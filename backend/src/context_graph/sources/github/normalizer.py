"""GitHub raw records → items (repos, issues, pull requests, comments, reviews, commits) and people."""

from __future__ import annotations

import re
from typing import Any

from context_graph.domain import EdgeKind, Item, NodeKind, PersonRecord, PersonRef, Relation, Source
from context_graph.domain import keys
from context_graph.sources.base import NormalizedBatch, RawRecords
from context_graph.sources.text import first_line, parse_datetime

_ISSUE_URL = re.compile(r"/repos/([^/]+)/([^/]+)/issues/(\d+)$")
_PULL_URL = re.compile(r"/repos/([^/]+)/([^/]+)/pulls/(\d+)$")


def repository_id(full_name: str) -> str:
    return keys.node_id(Source.GITHUB, NodeKind.REPOSITORY, full_name.lower())


def numbered_id(kind: NodeKind, full_name: str, number: int | str) -> str:
    return keys.node_id(Source.GITHUB, kind, f"{full_name.lower()}#{number}")


class GitHubNormalizer:
    def normalize(self, records: RawRecords) -> NormalizedBatch:
        batch = NormalizedBatch()
        pull_requests = list(records.get("pull_requests", []))
        pr_numbers = {(pr["repository"].lower(), int(pr["number"])) for pr in pull_requests}

        repos = {r["repository"] for stream in records.values() for r in stream if r.get("repository")}
        batch.items.extend(self._repository(full_name) for full_name in sorted(repos))

        for issue in records.get("issues", []):
            if issue.get("pull_request"):
                continue  # the issues API also lists PRs; they come from the pull_requests stream
            batch.items.append(self._numbered(issue, NodeKind.ISSUE))
            self._collect_user(batch, issue.get("user"))

        for pr in pull_requests:
            item = self._numbered(pr, NodeKind.PULL_REQUEST)
            item.props.update(
                merged=bool(pr.get("merged_at")),
                head=(pr.get("head") or {}).get("ref"),
                base=(pr.get("base") or {}).get("ref"),
            )
            batch.items.append(item)
            self._collect_user(batch, pr.get("user"))

        for comment in records.get("comments", []):
            parent = self._parent_from_issue_url(comment.get("issue_url", ""), pr_numbers)
            batch.items.append(self._comment(comment, parent, prefix=""))
            self._collect_user(batch, comment.get("user"))

        for review in records.get("reviews", []):
            if not (review.get("body") or "").strip():
                continue  # approvals without text carry no context
            parent = self._parent_from_pull_url(review.get("pull_request_url", ""))
            batch.items.append(self._comment(review, parent, prefix="review-"))
            self._collect_user(batch, review.get("user"))

        for commit in records.get("commits", []):
            batch.items.append(self._commit(commit))
            self._collect_commit_author(batch, commit)
        return batch

    # ------------------------------------------------------------ items

    @staticmethod
    def _repository(full_name: str) -> Item:
        owner, name = full_name.split("/", 1)
        url = f"https://github.com/{full_name}"
        return Item(
            id=repository_id(full_name),
            source=Source.GITHUB,
            kind=NodeKind.REPOSITORY,
            title=full_name,
            url=url,
            keys={keys.github_repo(owner, name), keys.github_repo_name(name), *keys.url_keys(url)},
            props={"owner": owner, "name": name},
            scan_text=False,
        )

    @staticmethod
    def _numbered(record: dict[str, Any], kind: NodeKind) -> Item:
        full_name = record["repository"]
        owner, name = full_name.split("/", 1)
        number = int(record["number"])
        url = record.get("html_url") or ""
        title = record.get("title") or ""
        label = "PR" if kind is NodeKind.PULL_REQUEST else "Issue"
        return Item(
            id=numbered_id(kind, full_name, number),
            source=Source.GITHUB,
            kind=kind,
            title=title,
            body=record.get("body") or "",
            url=url,
            created_at=parse_datetime(record.get("created_at")),
            updated_at=parse_datetime(record.get("updated_at")),
            keys={
                keys.github_number(owner, name, number),
                keys.github_repo_number(name, number),
                keys.title(title),
                *keys.url_keys(url),
            },
            authors=[_user_ref(record.get("user"))] if record.get("user") else [],
            assignees=[_user_ref(a) for a in record.get("assignees") or [] if a],
            relations=[Relation(EdgeKind.PART_OF, repository_id(full_name))],
            props={"ref": f"{label} #{number}", "number": number, "state": record.get("state"), "repo": full_name},
        )

    @staticmethod
    def _comment(record: dict[str, Any], parent: str | None, prefix: str) -> Item:
        body = record.get("body") or ""
        return Item(
            id=keys.node_id(Source.GITHUB, NodeKind.COMMENT, f"{prefix}{record['id']}"),
            source=Source.GITHUB,
            kind=NodeKind.COMMENT,
            title=first_line(body, 80) or "Comment",
            body=body,
            url=record.get("html_url"),
            created_at=parse_datetime(record.get("created_at") or record.get("submitted_at")),
            updated_at=parse_datetime(record.get("updated_at") or record.get("submitted_at")),
            authors=[_user_ref(record.get("user"))] if record.get("user") else [],
            relations=[Relation(EdgeKind.PART_OF, parent)] if parent else [],
            props={"repo": record.get("repository")},
        )

    @staticmethod
    def _commit(record: dict[str, Any]) -> Item:
        full_name = record["repository"]
        commit = record.get("commit") or {}
        message = commit.get("message") or ""
        author = commit.get("author") or {}
        login = (record.get("author") or {}).get("login")
        sha = record["sha"]
        ref = PersonRef(
            Source.GITHUB,
            native_id=str((record.get("author") or {}).get("id") or "") or None,
            email=author.get("email"),
            name=author.get("name"),
            handle=login,
        )
        return Item(
            id=keys.node_id(Source.GITHUB, NodeKind.COMMIT, sha),
            source=Source.GITHUB,
            kind=NodeKind.COMMIT,
            title=first_line(message, 100),
            body=message,
            url=record.get("html_url"),
            created_at=parse_datetime(author.get("date") or record.get("created_at")),
            updated_at=parse_datetime(author.get("date") or record.get("created_at")),
            keys={f"commit:{sha[:7]}", f"commit:{sha}", *keys.url_keys(record.get("html_url") or "")},
            authors=[ref],
            relations=[Relation(EdgeKind.PART_OF, repository_id(full_name))],
            props={"ref": sha[:7], "sha": sha, "branch": record.get("branch"), "repo": full_name},
        )

    # ------------------------------------------------------------ parents & people

    @staticmethod
    def _parent_from_issue_url(url: str, pr_numbers: set[tuple[str, int]]) -> str | None:
        if not (m := _ISSUE_URL.search(url)):
            return None
        full_name, number = f"{m[1]}/{m[2]}", int(m[3])
        kind = NodeKind.PULL_REQUEST if (full_name.lower(), number) in pr_numbers else NodeKind.ISSUE
        return numbered_id(kind, full_name, number)

    @staticmethod
    def _parent_from_pull_url(url: str) -> str | None:
        if not (m := _PULL_URL.search(url)):
            return None
        return numbered_id(NodeKind.PULL_REQUEST, f"{m[1]}/{m[2]}", m[3])

    @staticmethod
    def _collect_user(batch: NormalizedBatch, user: dict[str, Any] | None) -> None:
        if not user or user.get("type") == "Bot":
            return
        batch.people.append(
            PersonRecord(Source.GITHUB, native_id=str(user["id"]), handles={user.get("login") or ""} - {""})
        )

    @staticmethod
    def _collect_commit_author(batch: NormalizedBatch, record: dict[str, Any]) -> None:
        author = (record.get("commit") or {}).get("author") or {}
        account = record.get("author") or {}
        if not (account.get("id") or author.get("email")):
            return
        batch.people.append(
            PersonRecord(
                Source.GITHUB,
                native_id=str(account.get("id") or author.get("email")),
                names={author.get("name") or ""} - {""},
                emails={(author.get("email") or "").lower()} - {""},
                handles={account.get("login") or ""} - {""},
            )
        )


def _user_ref(user: dict[str, Any]) -> PersonRef:
    return PersonRef(Source.GITHUB, native_id=str(user.get("id")), handle=user.get("login"))
