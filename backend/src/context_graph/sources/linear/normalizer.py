"""Linear raw records → items (issues, comments, projects) and people."""

from __future__ import annotations

from typing import Any

from context_graph.domain import EdgeKind, Item, NodeKind, PersonRecord, PersonRef, Relation, Source
from context_graph.domain import keys
from context_graph.sources.base import NormalizedBatch, RawRecords
from context_graph.sources.text import first_line, parse_datetime

LINEAR_APP_DOMAIN = "@linear.linear.app"


def issue_id(identifier: str) -> str:
    return keys.node_id(Source.LINEAR, NodeKind.ISSUE, identifier.upper())


def project_id(native_id: str) -> str:
    return keys.node_id(Source.LINEAR, NodeKind.PROJECT, native_id)


class LinearNormalizer:
    def normalize(self, records: RawRecords) -> NormalizedBatch:
        batch = NormalizedBatch()
        issues = list(records.get("issues", []))
        identifier_by_id = {i["id"]: i["identifier"] for i in issues if i.get("identifier")}

        for project in records.get("projects", []):
            batch.items.append(self._project(project))
        for issue in issues:
            batch.items.append(self._issue(issue, identifier_by_id))
        for comment in records.get("comments", []):
            if item := self._comment(comment, identifier_by_id):
                batch.items.append(item)
        for user in records.get("users", []):
            if (user.get("email") or "").endswith(LINEAR_APP_DOMAIN):
                continue  # Linear's own app/integration users
            batch.people.append(
                PersonRecord(
                    Source.LINEAR,
                    native_id=user["id"],
                    names={user.get("name") or "", user.get("displayname") or ""} - {""},
                    emails={(user.get("email") or "").lower()} - {""},
                )
            )
        return batch

    @staticmethod
    def _issue(record: dict[str, Any], identifier_by_id: dict[str, str]) -> Item:
        identifier = record["identifier"]
        title = record.get("title") or ""
        url = record.get("url") or ""
        relations = []
        if parent := identifier_by_id.get(record.get("parentid") or ""):
            relations.append(Relation(EdgeKind.PART_OF, issue_id(parent)))
        if record.get("projectid"):
            relations.append(Relation(EdgeKind.PART_OF, project_id(record["projectid"])))
        return Item(
            id=issue_id(identifier),
            source=Source.LINEAR,
            kind=NodeKind.ISSUE,
            title=title,
            body=record.get("description") or "",
            url=url,
            created_at=parse_datetime(record.get("createdat")),
            updated_at=parse_datetime(record.get("updatedat")),
            keys={keys.issue(identifier), keys.title(title), *keys.url_keys(url)},
            authors=[PersonRef(Source.LINEAR, native_id=record["creatorid"])] if record.get("creatorid") else [],
            assignees=[PersonRef(Source.LINEAR, native_id=record["assigneeid"])] if record.get("assigneeid") else [],
            relations=relations,
            props={
                "ref": identifier,
                "priority": record.get("prioritylabel"),
                "branch": record.get("branchname"),
            },
        )

    @staticmethod
    def _comment(record: dict[str, Any], identifier_by_id: dict[str, str]) -> Item | None:
        identifier = identifier_by_id.get(record.get("issueid") or "")
        body = record.get("body") or ""
        return Item(
            id=keys.node_id(Source.LINEAR, NodeKind.COMMENT, record["id"]),
            source=Source.LINEAR,
            kind=NodeKind.COMMENT,
            title=first_line(body, 80) or "Comment",
            body=body,
            url=record.get("url"),
            created_at=parse_datetime(record.get("createdat")),
            updated_at=parse_datetime(record.get("updatedat")),
            authors=[PersonRef(Source.LINEAR, native_id=record["userid"])] if record.get("userid") else [],
            relations=[Relation(EdgeKind.PART_OF, issue_id(identifier))] if identifier else [],
            props={"issue": identifier},
        )

    @staticmethod
    def _project(record: dict[str, Any]) -> Item:
        name = record.get("name") or "Project"
        url = record.get("url") or ""
        return Item(
            id=project_id(record["id"]),
            source=Source.LINEAR,
            kind=NodeKind.PROJECT,
            title=name,
            body="\n".join(filter(None, [record.get("description"), record.get("content")])),
            url=url,
            created_at=parse_datetime(record.get("createdat")),
            updated_at=parse_datetime(record.get("updatedat")),
            keys={keys.title(name), *keys.url_keys(url)} if url else {keys.title(name)},
            authors=[PersonRef(Source.LINEAR, native_id=record["leadid"])] if record.get("leadid") else [],
        )
