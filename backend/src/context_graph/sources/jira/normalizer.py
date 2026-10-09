"""Jira raw records → items (projects, issues, comments) and people."""

from __future__ import annotations

import json
from typing import Any

from context_graph.domain import EdgeKind, Item, NodeKind, PersonRecord, PersonRef, Relation, Source
from context_graph.domain import keys
from context_graph.sources.base import NormalizedBatch, RawRecords
from context_graph.sources.text import adf_to_text, first_line, parse_datetime


def issue_id(key: str) -> str:
    return keys.node_id(Source.JIRA, NodeKind.ISSUE, key.upper())


def project_id(key: str) -> str:
    return keys.node_id(Source.JIRA, NodeKind.PROJECT, key.upper())


class JiraNormalizer:
    def __init__(self, domain: str) -> None:
        self._domain = domain

    def normalize(self, records: RawRecords) -> NormalizedBatch:
        batch = NormalizedBatch()
        issues = list(records.get("issues", []))
        key_by_id = {i["id"]: i["key"] for i in issues}

        for project in records.get("projects", []):
            batch.items.append(self._project(project))
        for issue in issues:
            batch.items.append(self._issue(issue))
            for field in ("reporter", "creator", "assignee"):
                if person := _person_record((issue.get("fields") or {}).get(field)):
                    batch.people.append(person)
        for comment in records.get("issue_comments", []):
            if item := self._comment(comment, key_by_id):
                batch.items.append(item)
        for user in records.get("users", []):
            if user.get("accounttype") != "atlassian":
                continue  # skip apps and bots
            batch.people.append(
                PersonRecord(
                    Source.JIRA,
                    native_id=user["accountid"],
                    names={user.get("displayname") or ""} - {""},
                    emails={(user.get("emailaddress") or "").lower()} - {""},
                )
            )
        return batch

    def _browse_url(self, key: str) -> str:
        return f"https://{self._domain}/browse/{key}" if self._domain else ""

    def _issue(self, record: dict[str, Any]) -> Item:
        fields = record.get("fields") or {}
        key = record["key"]
        title = fields.get("summary") or ""
        url = self._browse_url(key)
        relations = [Relation(EdgeKind.PART_OF, project_id(record.get("projectkey") or key.split("-")[0]))]
        if parent_key := (fields.get("parent") or {}).get("key"):
            relations.append(Relation(EdgeKind.PART_OF, issue_id(parent_key)))
        authors = [ref for ref in (_person_ref(fields.get("reporter")), _person_ref(fields.get("creator"))) if ref]
        return Item(
            id=issue_id(key),
            source=Source.JIRA,
            kind=NodeKind.ISSUE,
            title=title,
            body=adf_to_text(fields.get("description")).strip(),
            url=url,
            created_at=parse_datetime(fields.get("created") or record.get("created")),
            updated_at=parse_datetime(fields.get("updated") or record.get("updated")),
            keys={keys.issue(key), keys.title(title), *(keys.url_keys(url) if url else set())},
            authors=list(dict.fromkeys(authors)),
            assignees=[ref for ref in [_person_ref(fields.get("assignee"))] if ref],
            relations=relations,
            props={
                "ref": key,
                "status": (fields.get("status") or {}).get("name"),
                "type": (fields.get("issuetype") or {}).get("name"),
            },
        )

    def _comment(self, record: dict[str, Any], key_by_id: dict[str, str]) -> Item | None:
        key = key_by_id.get(str(record.get("issueid")))
        author = record.get("author")
        if isinstance(author, str):
            author = _json(author)
        body = adf_to_text(record.get("body")).strip()
        return Item(
            id=keys.node_id(Source.JIRA, NodeKind.COMMENT, str(record["id"])),
            source=Source.JIRA,
            kind=NodeKind.COMMENT,
            title=first_line(body, 80) or "Comment",
            body=body,
            url=f"{self._browse_url(key)}?focusedCommentId={record['id']}" if key else None,
            created_at=parse_datetime(record.get("created")),
            updated_at=parse_datetime(record.get("updated")),
            authors=[ref for ref in [_person_ref(author)] if ref],
            relations=[Relation(EdgeKind.PART_OF, issue_id(key))] if key else [],
            props={"issue": key},
        )

    def _project(self, record: dict[str, Any]) -> Item:
        key = record["key"]
        name = record.get("name") or key
        return Item(
            id=project_id(key),
            source=Source.JIRA,
            kind=NodeKind.PROJECT,
            title=name,
            body=record.get("description") or "",
            url=f"https://{self._domain}/jira/software/projects/{key}" if self._domain else None,
            keys={keys.title(name)},
            props={"ref": key},
            scan_text=False,
        )


def _person_ref(user: dict[str, Any] | None) -> PersonRef | None:
    if not user or not user.get("accountId"):
        return None
    return PersonRef(
        Source.JIRA,
        native_id=user["accountId"],
        email=user.get("emailAddress"),
        name=user.get("displayName"),
    )


def _person_record(user: dict[str, Any] | None) -> PersonRecord | None:
    if not user or not user.get("accountId") or user.get("accountType") == "app":
        return None
    return PersonRecord(
        Source.JIRA,
        native_id=user["accountId"],
        names={user.get("displayName") or ""} - {""},
        emails={(user.get("emailAddress") or "").lower()} - {""},
    )


def _json(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None
