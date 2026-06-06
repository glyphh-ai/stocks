"use client";

import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { CRED_FIELDS, type CredentialMeta, type CredKind } from "@/lib/types";
import { Field, Select, TextInput } from "./fields";

const KINDS: Exclude<CredKind, "none">[] = ["bearer", "basic", "header"];

const KIND_LABEL: Record<Exclude<CredKind, "none">, string> = {
  bearer: "Bearer token",
  basic: "Username + password",
  header: "Custom header",
};

export function CredentialsButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        onClick={() => setOpen(true)}
        title="Manage credentials"
        className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-border bg-surface-2 text-text-muted hover:text-text"
      >
        🔑
      </button>
      {open && <CredentialsModal onClose={() => setOpen(false)} />}
    </>
  );
}

function CredentialsModal({ onClose }: { onClose: () => void }) {
  const { data: creds, mutate } = useSWR<CredentialMeta[]>("/credentials", () =>
    api.credentials(),
  );
  const list = creds ?? [];

  const [name, setName] = useState("");
  const [kind, setKind] = useState<Exclude<CredKind, "none">>("bearer");
  const [fields, setFields] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const setField = (k: string, v: string) => setFields((f) => ({ ...f, [k]: v }));
  const pickKind = (k: Exclude<CredKind, "none">) => {
    setKind(k);
    setFields({});
  };

  const required = CRED_FIELDS[kind];
  const canSave = name.trim() !== "" && required.every((f) => (fields[f] ?? "") !== "");

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.saveCredential(name.trim(), kind, fields);
      setName("");
      setFields({});
      mutate();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (n: string) => {
    await api.deleteCredential(n);
    mutate();
  };

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-label="Manage credentials"
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[80vh] w-full max-w-md flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-xl"
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div>
            <h2 className="text-sm font-semibold">Credentials</h2>
            <p className="text-xs text-text-muted">
              Secrets are encrypted and never shown again.
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="grid h-7 w-7 place-items-center rounded text-text-muted hover:text-text"
          >
            ×
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {list.length === 0 ? (
            <p className="rounded-lg border border-dashed border-border px-3 py-4 text-center text-xs text-text-muted">
              No credentials yet.
            </p>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {list.map((c) => (
                <li
                  key={c.name}
                  className="flex items-center gap-2 rounded-lg border border-border bg-surface-2 px-3 py-2"
                >
                  <span className="truncate text-sm font-medium">{c.name}</span>
                  <span className="rounded bg-surface-3 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
                    {c.kind}
                  </span>
                  <button
                    onClick={() => remove(c.name)}
                    aria-label={`Delete ${c.name}`}
                    title="Delete"
                    className="ml-auto grid h-6 w-6 place-items-center rounded text-text-muted hover:text-bad"
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          )}

          <div className="mt-4 flex flex-col gap-2.5 border-t border-border pt-4">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">
              Add credential
            </span>
            <Field label="Name">
              <TextInput
                value={name}
                placeholder="my-api-key"
                onChange={(e) => setName(e.target.value)}
              />
            </Field>
            <Field label="Kind">
              <Select
                value={kind}
                onChange={(e) => pickKind(e.target.value as Exclude<CredKind, "none">)}
              >
                {KINDS.map((k) => (
                  <option key={k} value={k}>
                    {KIND_LABEL[k]}
                  </option>
                ))}
              </Select>
            </Field>
            {required.map((f) => (
              <Field key={f} label={f}>
                <TextInput
                  type={f === "name" ? "text" : "password"}
                  autoComplete="off"
                  value={fields[f] ?? ""}
                  placeholder={f}
                  onChange={(e) => setField(f, e.target.value)}
                />
              </Field>
            ))}
            {error && <p className="text-xs text-bad">{error}</p>}
            <button
              onClick={save}
              disabled={!canSave || busy}
              className="rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-40"
            >
              {busy ? "Saving…" : "Add credential"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
