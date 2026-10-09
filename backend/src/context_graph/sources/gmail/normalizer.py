"""Gmail raw records → email thread and email items, and the people in them."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from context_graph.domain import EdgeKind, Item, NodeKind, PersonRecord, PersonRef, Relation, Source
from context_graph.domain import keys
from context_graph.sources.base import NormalizedBatch, RawRecords
from context_graph.sources.text import clean_subject, gmail_body, gmail_headers, parse_addresses, parse_datetime


def thread_id(native_id: str) -> str:
    return keys.node_id(Source.GMAIL, NodeKind.EMAIL_THREAD, native_id)


def email_id(native_id: str) -> str:
    return keys.node_id(Source.GMAIL, NodeKind.EMAIL, native_id)


class GmailNormalizer:
    def __init__(self, skip_labels: set[str]) -> None:
        self._skip_labels = skip_labels

    def normalize(self, records: RawRecords) -> NormalizedBatch:
        batch = NormalizedBatch()
        by_thread: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for message in records.get("messages_details", []):
            if self._skip_labels & set(message.get("labelids") or []):
                continue
            by_thread[message["threadid"]].append(message)

        people: dict[str, PersonRecord] = {}
        for native_thread, messages in by_thread.items():
            messages.sort(key=lambda m: int(m.get("internaldate") or 0))
            emails = [self._email(m) for m in messages]
            batch.items.extend(emails)
            batch.items.append(self._thread(native_thread, emails))
            for message in messages:
                headers = gmail_headers(message.get("payload") or {})
                for header in ("from", "to", "cc"):
                    for name, address in parse_addresses(headers.get(header, "")):
                        record = people.setdefault(address, PersonRecord(Source.GMAIL, native_id=address, emails={address}))
                        if name:
                            record.names.add(name)
        batch.people.extend(people.values())
        return batch

    @staticmethod
    def _email(record: dict[str, Any]) -> Item:
        payload = record.get("payload") or {}
        headers = gmail_headers(payload)
        senders = parse_addresses(headers.get("from", ""))
        recipients = parse_addresses(headers.get("to", "")) + parse_addresses(headers.get("cc", ""))
        sent = parse_datetime(record.get("internaldate")) or parse_datetime(headers.get("date"))
        subject = headers.get("subject") or "(no subject)"
        return Item(
            id=email_id(record["id"]),
            source=Source.GMAIL,
            kind=NodeKind.EMAIL,
            title=subject,
            body=gmail_body(payload) or record.get("snippet") or "",
            url=f"https://mail.google.com/mail/u/0/#all/{record['threadid']}",
            created_at=sent,
            updated_at=sent,
            authors=[PersonRef(Source.GMAIL, native_id=email, email=email, name=name or None) for name, email in senders],
            relations=[Relation(EdgeKind.PART_OF, thread_id(record["threadid"]))],
            props={
                "from": ", ".join(e for _, e in senders),
                "to": ", ".join(e for _, e in recipients),
                "labels": record.get("labelids") or [],
            },
        )

    @staticmethod
    def _thread(native_id: str, emails: list[Item]) -> Item:
        subject = clean_subject(emails[0].title) if emails else "(no subject)"
        authors = list(dict.fromkeys(a for e in emails for a in e.authors))
        return Item(
            id=thread_id(native_id),
            source=Source.GMAIL,
            kind=NodeKind.EMAIL_THREAD,
            title=subject,
            url=f"https://mail.google.com/mail/u/0/#all/{native_id}",
            created_at=emails[0].created_at if emails else None,
            updated_at=emails[-1].updated_at if emails else None,
            keys={keys.title(subject)},
            authors=authors,
            props={"messages": len(emails)},
            scan_text=False,
        )
