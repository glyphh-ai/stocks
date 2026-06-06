"use client";

import useSWR from "swr";
import { api } from "@/lib/api";
import type { CredentialMeta, JobStep, Role, ToolSpec } from "@/lib/types";
import { Field, Select, Textarea, TextInput } from "./fields";

const KIND_LABEL: Record<JobStep["kind"], string> = {
  tool: "Tool",
  llm: "LLM judge",
  set_role: "Set role",
};

const KIND_HINT: Record<JobStep["kind"], string> = {
  tool: "Fetch a signal from a registered source",
  llm: "Score fetched data into a structured value",
  set_role: "Write a value into one of this segment's roles",
};

function defaultArgs(spec: ToolSpec | undefined): Record<string, string> {
  const args: Record<string, string> = {};
  for (const p of spec?.params ?? []) {
    args[p.name] = p.type === "symbol" || p.name === "symbol" ? "{symbol}" : "";
  }
  return args;
}

function newStep(kind: JobStep["kind"], tools: ToolSpec[]): JobStep {
  if (kind === "tool") {
    const spec = tools[0];
    return { kind: "tool", name: spec?.name ?? "", args: defaultArgs(spec), out: spec?.name ?? "out" };
  }
  if (kind === "llm") {
    return { kind: "llm", system: "", prompt: "", schema: { score: "int[1..10]" }, out: "verdict" };
  }
  return { kind: "set_role", role: "", value: "" };
}

export function StepList({
  job,
  roles,
  onChange,
}: {
  job: JobStep[];
  roles: Role[];
  onChange: (job: JobStep[]) => void;
}) {
  const { data: tools } = useSWR<ToolSpec[]>("/tools", () => api.tools());
  const toolList = tools ?? [];

  const patch = (i: number, step: JobStep) => {
    const next = job.slice();
    next[i] = step;
    onChange(next);
  };
  const add = (kind: JobStep["kind"]) => onChange([...job, newStep(kind, toolList)]);
  const removeAt = (i: number) => onChange(job.filter((_, j) => j !== i));
  const move = (i: number, dir: -1 | 1) => {
    const j = i + dir;
    if (j < 0 || j >= job.length) return;
    const next = job.slice();
    [next[i], next[j]] = [next[j], next[i]];
    onChange(next);
  };

  return (
    <div className="flex flex-col gap-2">
      {job.length === 0 && (
        <p className="rounded-lg border border-dashed border-border px-3 py-4 text-center text-xs text-text-muted">
          No steps yet. Add a tool to fetch a signal, an LLM judge to score it, then set roles.
        </p>
      )}

      {job.map((step, i) => (
        <div key={i} className="rounded-lg border border-border bg-surface-2">
          <div className="flex items-center gap-2 border-b border-border px-3 py-1.5">
            <span className="rounded bg-surface-3 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
              {KIND_LABEL[step.kind]}
            </span>
            <span className="truncate text-xs text-text-muted">{KIND_HINT[step.kind]}</span>
            <div className="ml-auto flex items-center gap-0.5">
              <IconBtn label="Move up" disabled={i === 0} onClick={() => move(i, -1)}>↑</IconBtn>
              <IconBtn label="Move down" disabled={i === job.length - 1} onClick={() => move(i, 1)}>↓</IconBtn>
              <IconBtn label="Remove step" danger onClick={() => removeAt(i)}>×</IconBtn>
            </div>
          </div>

          <div className="flex flex-col gap-2.5 p-3">
            {step.kind === "tool" && (
              <ToolStep step={step} tools={toolList} onChange={(s) => patch(i, s)} />
            )}
            {step.kind === "llm" && <LlmStep step={step} onChange={(s) => patch(i, s)} />}
            {step.kind === "set_role" && (
              <SetRoleStep step={step} roles={roles} onChange={(s) => patch(i, s)} />
            )}
          </div>
        </div>
      ))}

      <div className="flex gap-1.5">
        <AddBtn onClick={() => add("tool")}>+ Tool</AddBtn>
        <AddBtn onClick={() => add("llm")}>+ LLM judge</AddBtn>
        <AddBtn onClick={() => add("set_role")}>+ Set role</AddBtn>
      </div>
    </div>
  );
}

function ToolStep({
  step,
  tools,
  onChange,
}: {
  step: Extract<JobStep, { kind: "tool" }>;
  tools: ToolSpec[];
  onChange: (s: JobStep) => void;
}) {
  const spec = tools.find((t) => t.name === step.name);
  const needsCred = spec ? spec.cred_kind !== "none" : false;
  const { data: creds } = useSWR<CredentialMeta[]>(
    needsCred ? "/credentials" : null,
    () => api.credentials(),
  );
  const matchingCreds = (creds ?? []).filter((c) => c.kind === spec?.cred_kind);
  const selectTool = (name: string) => {
    const next = tools.find((t) => t.name === name);
    onChange({ kind: "tool", name, args: defaultArgs(next), out: next?.name ?? step.out });
  };
  const setArg = (k: string, v: string) =>
    onChange({ ...step, args: { ...(step.args ?? {}), [k]: v } });

  return (
    <>
      <Field label="Tool">
        <Select value={step.name} onChange={(e) => selectTool(e.target.value)}>
          {!spec && <option value={step.name}>{step.name || "— select —"}</option>}
          {tools.map((t) => (
            <option key={t.name} value={t.name}>
              {t.name}
            </option>
          ))}
        </Select>
      </Field>
      {spec?.description && <p className="-mt-1 text-xs text-text-muted">{spec.description}</p>}

      {(spec?.params ?? []).map((p) => (
        <Field key={p.name} label={`arg · ${p.name}`}>
          <TextInput
            value={String((step.args ?? {})[p.name] ?? "")}
            placeholder={p.type === "symbol" ? "{symbol}" : p.type}
            onChange={(e) => setArg(p.name, e.target.value)}
          />
        </Field>
      ))}

      {needsCred && (
        <Field label={`Credential · ${spec!.cred_kind}`}>
          <Select
            value={step.credential ?? ""}
            onChange={(e) => onChange({ ...step, credential: e.target.value || undefined })}
          >
            <option value="">— none —</option>
            {matchingCreds.map((c) => (
              <option key={c.name} value={c.name}>
                {c.name}
              </option>
            ))}
          </Select>
        </Field>
      )}
      {needsCred && matchingCreds.length === 0 && (
        <p className="-mt-1 text-xs text-text-muted">
          No {spec!.cred_kind} credentials yet — add one with the 🔑 button.
        </p>
      )}

      <Field label="Store result as">
        <TextInput value={step.out} onChange={(e) => onChange({ ...step, out: e.target.value })} />
      </Field>

      {spec && spec.outputs.length > 0 && (
        <p className="text-xs text-text-muted">
          Returns:{" "}
          {spec.outputs.map((o) => (
            <code key={o} className="mr-1 rounded bg-surface-3 px-1 text-text">
              {o.startsWith("(") ? `{${step.out}}` : `{${step.out}.${o}}`}
            </code>
          ))}
        </p>
      )}
    </>
  );
}

function LlmStep({
  step,
  onChange,
}: {
  step: Extract<JobStep, { kind: "llm" }>;
  onChange: (s: JobStep) => void;
}) {
  const schema = step.schema ?? {};
  const entries = Object.entries(schema);
  const setSchema = (next: Record<string, string>) => onChange({ ...step, schema: next });
  const renameKey = (oldK: string, newK: string) => {
    const next: Record<string, string> = {};
    for (const [k, v] of Object.entries(schema)) next[k === oldK ? newK : k] = v;
    setSchema(next);
  };

  return (
    <>
      <Field label="System prompt">
        <Textarea
          value={step.system ?? ""}
          rows={2}
          placeholder="You are an equity analyst…"
          onChange={(e) => onChange({ ...step, system: e.target.value })}
        />
      </Field>
      <Field label="Prompt">
        <Textarea
          value={step.prompt ?? ""}
          rows={3}
          placeholder="Symbol: {symbol}. Headlines: {news}. Score 1–10."
          onChange={(e) => onChange({ ...step, prompt: e.target.value })}
        />
      </Field>

      <div>
        <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-text-muted">
          Output schema
        </span>
        <div className="flex flex-col gap-1.5">
          {entries.map(([k, v]) => (
            <div key={k} className="flex items-center gap-1.5">
              <TextInput
                value={k}
                placeholder="field"
                className="flex-1"
                onChange={(e) => renameKey(k, e.target.value)}
              />
              <TextInput
                value={v}
                placeholder="int[1..10]"
                className="flex-1"
                onChange={(e) => setSchema({ ...schema, [k]: e.target.value })}
              />
              <IconBtn
                label="Remove field"
                danger
                onClick={() => {
                  const next = { ...schema };
                  delete next[k];
                  setSchema(next);
                }}
              >
                ×
              </IconBtn>
            </div>
          ))}
          <AddBtn onClick={() => setSchema({ ...schema, [`field${entries.length + 1}`]: "int" })}>
            + field
          </AddBtn>
        </div>
        <p className="mt-1 text-xs text-text-muted">
          Types: <code className="text-text">int</code>, <code className="text-text">float</code>,{" "}
          <code className="text-text">int[1..10]</code>, <code className="text-text">float[-1..1]</code>.
        </p>
      </div>

      <Field label="Store result as">
        <TextInput value={step.out} onChange={(e) => onChange({ ...step, out: e.target.value })} />
      </Field>
    </>
  );
}

function SetRoleStep({
  step,
  roles,
  onChange,
}: {
  step: Extract<JobStep, { kind: "set_role" }>;
  roles: Role[];
  onChange: (s: JobStep) => void;
}) {
  return (
    <>
      <Field label="Role">
        <Select value={step.role} onChange={(e) => onChange({ ...step, role: e.target.value })}>
          <option value="">— select —</option>
          {roles.map((r) => (
            <option key={r.key} value={r.key}>
              {r.key}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Value">
        <TextInput
          value={step.value}
          placeholder="{verdict.score}"
          onChange={(e) => onChange({ ...step, value: e.target.value })}
        />
      </Field>
    </>
  );
}

function IconBtn({
  children,
  label,
  onClick,
  disabled,
  danger,
}: {
  children: React.ReactNode;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className={`grid h-6 w-6 place-items-center rounded text-sm transition-colors disabled:opacity-25 ${
        danger ? "text-text-muted hover:text-bad" : "text-text-muted hover:text-text"
      }`}
    >
      {children}
    </button>
  );
}

function AddBtn({ children, onClick }: { children: React.ReactNode; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-md border border-dashed border-border px-2 py-1 text-xs font-medium text-text-muted transition-colors hover:border-accent hover:text-accent"
    >
      {children}
    </button>
  );
}
