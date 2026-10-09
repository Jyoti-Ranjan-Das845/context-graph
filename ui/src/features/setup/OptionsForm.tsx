import { useEffect, useState } from "react";
import type { JsonSchemaProperty } from "../../api/types";

type Values = Record<string, unknown>;

/** The field type, looking through `anyOf` for optional fields (e.g. `string | null`). */
function fieldType(prop: JsonSchemaProperty): string | undefined {
  return prop.type ?? prop.anyOf?.find((p) => p.type && p.type !== "null")?.type;
}

/** List fields are edited as comma-separated text and parsed back on save. */
function toDraft(schema: Record<string, JsonSchemaProperty>, values: Values): Values {
  const draft: Values = { ...values };
  for (const [key, prop] of Object.entries(schema)) {
    if (fieldType(prop) === "array") draft[key] = Array.isArray(values[key]) ? (values[key] as unknown[]).join(", ") : "";
  }
  return draft;
}

function fromDraft(schema: Record<string, JsonSchemaProperty>, draft: Values): Values {
  const values: Values = { ...draft };
  for (const [key, prop] of Object.entries(schema)) {
    const type = fieldType(prop);
    const value = draft[key];
    if (type === "array") values[key] = String(value ?? "").split(",").map((s) => s.trim()).filter(Boolean);
    else if (type === "string" && value === "") values[key] = null;
  }
  return values;
}

/** Renders a tool's options from its JSON schema: booleans, numbers, strings and string lists. */
export function OptionsForm({
  schema,
  values,
  onSave,
}: {
  schema: Record<string, JsonSchemaProperty>;
  values: Values;
  onSave: (values: Values) => Promise<void>;
}) {
  const [draft, setDraft] = useState<Values>(() => toDraft(schema, values));
  const [saving, setSaving] = useState(false);
  useEffect(() => setDraft(toDraft(schema, values)), [schema, values]);

  const fields = Object.entries(schema);
  if (!fields.length) return null;
  const parsed = fromDraft(schema, draft);
  const dirty = JSON.stringify(parsed) !== JSON.stringify(values);
  const set = (key: string, value: unknown) => setDraft({ ...draft, [key]: value });

  async function save() {
    setSaving(true);
    try {
      await onSave(parsed);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="options">
      <h4>Options</h4>
      {fields.map(([key, prop]) => {
        const type = fieldType(prop);
        const label = prop.title ?? key;
        const help = prop.description && <span className="muted small">{prop.description}</span>;
        const value = draft[key];
        if (type === "boolean") {
          return (
            <label key={key} className="toggle">
              <input type="checkbox" checked={Boolean(value)} onChange={(e) => set(key, e.target.checked)} />
              {label}
              {help}
            </label>
          );
        }
        return (
          <label key={key} className="field">
            <span>
              {label}
              {type === "array" && <span className="muted small"> (comma separated)</span>}
            </span>
            {type === "integer" || type === "number" ? (
              <input
                type="number"
                min={prop.minimum}
                max={prop.maximum}
                value={Number(value ?? 0)}
                onChange={(e) => set(key, Number(e.target.value))}
              />
            ) : (
              <input value={String(value ?? "")} placeholder={type === "array" ? "" : "default"} onChange={(e) => set(key, e.target.value)} />
            )}
            {help}
          </label>
        );
      })}
      <div className="row">
        <button className="secondary" disabled={!dirty || saving} onClick={save}>
          {saving ? "Saving…" : "Save options"}
        </button>
      </div>
    </div>
  );
}
