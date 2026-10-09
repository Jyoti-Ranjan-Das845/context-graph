"""Slack raw records → items (channels, messages, thread replies) and people."""

from __future__ import annotations

from typing import Any

from context_graph.domain import EdgeKind, Item, NodeKind, PersonRecord, PersonRef, Relation, Source
from context_graph.domain import keys
from context_graph.sources.base import NormalizedBatch, RawRecords
from context_graph.sources.text import first_line, parse_datetime, slack_to_text

SKIPPED_SUBTYPES = frozenset(
    {"channel_join", "channel_leave", "channel_topic", "channel_purpose", "channel_name", "bot_add", "bot_remove"}
)


def channel_id(native_id: str) -> str:
    return keys.node_id(Source.SLACK, NodeKind.CHANNEL, native_id)


def message_id(channel: str, ts: str) -> str:
    return keys.node_id(Source.SLACK, NodeKind.MESSAGE, f"{channel}:{ts}")


class SlackNormalizer:
    def normalize(self, records: RawRecords) -> NormalizedBatch:
        batch = NormalizedBatch()
        users = list(records.get("users", []))
        user_names = {u["id"]: _display_name(u) for u in users}
        channels = list(records.get("channels", []))
        channel_names = {c["id"]: c.get("name") or c["id"] for c in channels}
        team_by_channel = {c["id"]: c.get("context_team_id") for c in channels}

        for channel in channels:
            batch.items.append(self._channel(channel))

        messages: dict[tuple[str, str], dict[str, Any]] = {}
        for stream in ("channel_messages", "threads"):
            for message in records.get(stream, []):
                if message.get("subtype") in SKIPPED_SUBTYPES or not (message.get("text") or "").strip():
                    continue
                messages[(message["channel_id"], message["ts"])] = message
        for (channel, _), message in sorted(messages.items(), key=lambda kv: float(kv[0][1])):
            team = team_by_channel.get(channel) or message.get("team")
            batch.items.append(self._message(message, user_names, channel_names, team))

        for user in users:
            if user.get("is_bot") or user.get("id") == "USLACKBOT" or user.get("deleted"):
                continue
            profile = user.get("profile") or {}
            batch.people.append(
                PersonRecord(
                    Source.SLACK,
                    native_id=user["id"],
                    names={user.get("real_name") or "", profile.get("real_name") or "", profile.get("display_name") or ""}
                    - {""},
                    emails={(profile.get("email") or "").lower()} - {""},
                    handles={user.get("name") or ""} - {""},
                )
            )
        return batch

    @staticmethod
    def _channel(record: dict[str, Any]) -> Item:
        name = record.get("name") or record["id"]
        team = record.get("context_team_id")
        purpose = (record.get("purpose") or {}).get("value") or ""
        topic = (record.get("topic") or {}).get("value") or ""
        return Item(
            id=channel_id(record["id"]),
            source=Source.SLACK,
            kind=NodeKind.CHANNEL,
            title=f"#{name}",
            body="\n".join(filter(None, [purpose, topic])),
            url=f"https://app.slack.com/client/{team}/{record['id']}" if team else None,
            created_at=parse_datetime(record.get("created")),
            keys={keys.channel(name)},
            props={"private": bool(record.get("is_private"))},
            scan_text=False,
        )

    @staticmethod
    def _message(
        record: dict[str, Any], user_names: dict[str, str], channel_names: dict[str, str], team: str | None
    ) -> Item:
        channel, ts = record["channel_id"], record["ts"]
        text = slack_to_text(record.get("text") or "", user_names, channel_names)
        thread_ts = record.get("thread_ts")
        relations = [Relation(EdgeKind.PART_OF, channel_id(channel))]
        if thread_ts and thread_ts != ts:
            relations.append(Relation(EdgeKind.REPLY_TO, message_id(channel, thread_ts)))
        url = None
        if team:
            root = thread_ts or ts
            url = f"https://app.slack.com/client/{team}/{channel}/thread/{channel}-{root}"
        return Item(
            id=message_id(channel, ts),
            source=Source.SLACK,
            kind=NodeKind.MESSAGE,
            title=first_line(text, 90),
            body=text,
            url=url,
            created_at=parse_datetime(ts),
            updated_at=parse_datetime(ts),
            keys={keys.slack_message(channel, ts)},
            authors=[PersonRef(Source.SLACK, native_id=record["user"])] if record.get("user") else [],
            relations=relations,
            props={
                "channel": f"#{channel_names.get(channel, channel)}",
                "thread_ts": thread_ts,
                "replies": record.get("reply_count") or 0,
            },
        )


def _display_name(user: dict[str, Any]) -> str:
    profile = user.get("profile") or {}
    return profile.get("real_name") or user.get("real_name") or user.get("name") or user["id"]
