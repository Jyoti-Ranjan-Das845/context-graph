import { useState } from "react";
import { api, errorMessage } from "../../api/client";
import type { CredentialField, JsonSchemaProperty, SourceInfo, SourceRunStatus } from "../../api/types";
import { ErrorNote, StatusPill, timeAgo } from "../../components/ui";
import { SOURCE_COLORS } from "../graph/palette";
import { OptionsForm } from "./OptionsForm";

const NO_FIELDS: Record<string, JsonSchemaProperty> = {};

type Check = { ok: boolean; message: string };

function connectionPill(source: SourceInfo, check: Check | null) {
  if (check) return <StatusPill tone={check.ok ? "ok" : "error"}>{check.ok ? "Connected" : "Connection failed"}</StatusPill>;
  if (!source.enabled) return <StatusPill tone="muted">Off</StatusPill>;
  if (!source.configured) return <StatusPill tone="warn">Needs setup</StatusPill>;
  return <StatusPill tone="ok">Ready</StatusPill>;
}

const plural = (count: number, noun: string) => `${count} ${noun}${count === 1 ? "" : "s"}`;

function lastPullText(run: SourceRunStatus): string | null {
  if (run.pull === "error") return `Last pull failed: ${run.message ?? "unknown error"}`;
  if (run.normalize_error) return `Could not read the pulled data: ${run.normalize_error}`;
  if (run.pull === "ok") return `Pulled ${timeAgo(run.finished_at)}${run.items !== undefined ? ` · ${plural(run.items, "item")}` : ""}`;
  if (run.pull === "running") return "Pulling now…";
  return null;
}

export function SourceCard({ source, onChange }: { source: SourceInfo; onChange: (updated: SourceInfo) => void }) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [check, setCheck] = useState<Check | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(!source.configured);

  async function act(name: string, task: () => Promise<void>) {
    setBusy(name);
    setError(null);
    try {
      await task();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  const typed = Object.fromEntries(Object.entries(values).filter(([, v]) => v.trim()));
  const pullText = lastPullText(source.last_pull ?? {});
  const pullFailed = source.last_pull?.pull === "error" || Boolean(source.last_pull?.normalize_error);

  const saveCredentials = () =>
    act("save", async () => {
      onChange(await api.saveCredentials(source.id, typed));
      setValues({});
      setCheck(null);
    });
  const testConnection = () => act("check", async () => setCheck(await api.checkSource(source.id)));
  const signInWithGoogle = () => act("google", async () => onChange(await api.gmailSignIn()));
  const openSlackAppCreator = () => act("slack", async () => void window.open((await api.slackCreateAppUrl()).url, "_blank", "noopener"));

  const credentialInput = (field: CredentialField) => (
    <label key={field.env_key} className="field">
      <span>
        {field.label}
        {field.help_url && (
          <a className="small help-link" href={field.help_url} target="_blank" rel="noreferrer">
            where do I get this? ↗
          </a>
        )}
      </span>
      <input
        type={field.secret ? "password" : "text"}
        placeholder={field.is_set ? `${field.display ?? "saved"} (leave empty to keep)` : field.placeholder}
        value={values[field.env_key] ?? ""}
        onChange={(e) => setValues({ ...values, [field.env_key]: e.target.value })}
        autoComplete="off"
        spellCheck={false}
      />
      {field.help_text && <span className="muted small">{field.help_text}</span>}
    </label>
  );

  const googleSignIn = (field: CredentialField) => (
    <div key={field.env_key} className="field">
      <span>{field.label}</span>
      <div className="row">
        <StatusPill tone={field.is_set ? "ok" : "warn"}>{field.is_set ? "Signed in" : "Not signed in"}</StatusPill>
        <button className="secondary" disabled={busy !== null} onClick={signInWithGoogle}>
          {busy === "google" ? "Waiting for Google…" : field.is_set ? "Sign in again" : "Sign in with Google"}
        </button>
      </div>
      {field.help_text && <span className="muted small">{field.help_text}</span>}
    </div>
  );

  return (
    <article className="card">
      <button className="card-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="dot big" style={{ background: SOURCE_COLORS[source.id] }} />
        <h3>{source.label}</h3>
        {connectionPill(source, check)}
        {pullText && <span className={`small ${pullFailed ? "error-text" : "muted"}`}>{pullText}</span>}
        <span className="chevron">{open ? "▾" : "▸"}</span>
      </button>

      {open && (
        <div className="card-body">
          {source.setup_steps.length > 0 && (
            <ol className="steps">
              {source.setup_steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
          )}

          {source.id === "slack" && (
            <div className="row">
              <button className="secondary" disabled={busy !== null} onClick={openSlackAppCreator}>
                Create the Slack app (pre-filled) ↗
              </button>
            </div>
          )}

          {source.credentials.map((field) => (field.managed_by === "google_signin" ? googleSignIn(field) : credentialInput(field)))}

          <div className="row">
            <button className="primary" disabled={!Object.keys(typed).length || busy !== null} onClick={saveCredentials}>
              {busy === "save" ? "Saving…" : "Save"}
            </button>
            <button className="secondary" disabled={busy !== null || !source.configured} onClick={testConnection}>
              {busy === "check" ? "Testing…" : "Test connection"}
            </button>
            {check && <span className={`small ${check.ok ? "ok-text" : "error-text"}`}>{check.message}</span>}
          </div>

          <OptionsForm
            schema={source.options_schema.properties ?? NO_FIELDS}
            values={source.options}
            onSave={(next) => act("options", async () => onChange(await api.saveOptions(source.id, next)))}
          />
          <ErrorNote message={error} />
        </div>
      )}
    </article>
  );
}
