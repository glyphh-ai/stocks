"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { Group, Panel, Separator } from "react-resizable-panels";
import { api } from "@/lib/api";
import type { GlyphTemplate, TemplateMeta } from "@/lib/types";
import {
  clone,
  emptyTemplate,
  newLayer,
  newRole,
  newSegment,
  type Selection,
} from "@/lib/glyph";
import { BuilderTree } from "./BuilderTree";
import { CredentialsButton } from "./CredentialsManager";
import { NodeEditor } from "./NodeEditor";
import { TestPanel } from "./TestPanel";

export function ConfigTab() {
  const { data: templates, mutate } = useSWR<TemplateMeta[]>("/templates", () => api.templates());

  const [name, setName] = useState<string>("");
  const [template, setTemplate] = useState<GlyphTemplate | null>(null);
  const [selection, setSelection] = useState<Selection>({ kind: "root" });
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);

  // First load: pull the bundled "equity" seed so there's something to edit.
  useEffect(() => {
    if (template) return;
    (async () => {
      try {
        const t = await api.template("equity");
        setName(t.name);
        setTemplate(t.body);
      } catch {
        setName("untitled");
        setTemplate(emptyTemplate());
      }
    })();
  }, [template]);

  const loadTemplate = async (n: string) => {
    const t = await api.template(n);
    setName(t.name);
    setTemplate(t.body);
    setSelection({ kind: "root" });
    setDirty(false);
  };

  const change = (t: GlyphTemplate) => {
    setTemplate(t);
    setDirty(true);
  };

  const addLayer = () =>
    change(((t) => {
      t.layers.push(newLayer(t.layers.length + 1));
      return t;
    })(clone(template!)));

  const addSegment = (l: number) =>
    change(((t) => {
      t.layers[l].segments.push(newSegment(t.layers[l].segments.length + 1));
      return t;
    })(clone(template!)));

  const addRole = (l: number, s: number) =>
    change(((t) => {
      t.layers[l].segments[s].roles.push(newRole(t.layers[l].segments[s].roles.length + 1));
      return t;
    })(clone(template!)));

  const remove = (sel: Selection) => {
    const t = clone(template!);
    if (sel.kind === "layer") t.layers.splice(sel.l, 1);
    else if (sel.kind === "segment") t.layers[sel.l].segments.splice(sel.s, 1);
    else if (sel.kind === "role") t.layers[sel.l].segments[sel.s].roles.splice(sel.r, 1);
    change(t);
    setSelection({ kind: "root" });
  };

  const save = async () => {
    if (!template) return;
    setSaving(true);
    try {
      await api.saveTemplate(name || "untitled", template.symbol, template);
      setDirty(false);
      mutate();
    } finally {
      setSaving(false);
    }
  };

  const createNew = () => {
    setName("untitled");
    setTemplate(emptyTemplate());
    setSelection({ kind: "root" });
    setDirty(true);
  };

  if (!template) {
    return <div className="grid h-full place-items-center text-sm text-text-muted">Loading…</div>;
  }

  return (
    <Group orientation="horizontal" className="h-full">
      {/* Left: builder */}
      <Panel defaultSize={26} minSize={16}>
        <div className="flex h-full flex-col border-r border-border bg-surface">
          <div className="flex items-center gap-2 border-b border-border px-3 py-2.5">
            <select
              value={name}
              onChange={(e) => loadTemplate(e.target.value)}
              className="min-w-0 flex-1 rounded-lg border border-border bg-surface-2 px-2 py-1.5 text-sm outline-none focus:border-accent"
            >
              {!templates?.some((t) => t.name === name) && <option value={name}>{name}</option>}
              {templates?.map((t) => (
                <option key={t.name} value={t.name}>
                  {t.name}
                </option>
              ))}
            </select>
            <button
              onClick={createNew}
              title="New template"
              className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-border bg-surface-2 text-text-muted hover:text-text"
            >
              +
            </button>
            <CredentialsButton />
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-2">
            <BuilderTree
              template={template}
              selection={selection}
              onSelect={setSelection}
              onAddLayer={addLayer}
              onAddSegment={addSegment}
              onAddRole={addRole}
              onRemove={remove}
            />
          </div>
        </div>
      </Panel>

      <Separator />

      {/* Middle: editor */}
      <Panel defaultSize={44} minSize={24}>
        <div className="flex h-full flex-col bg-bg">
          <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-2.5">
            <input
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setDirty(true);
              }}
              className="min-w-0 flex-1 bg-transparent text-sm font-semibold outline-none"
            />
            <div className="flex items-center gap-2">
              {dirty && <span className="text-xs text-text-muted">unsaved</span>}
              <button
                onClick={save}
                disabled={saving || !dirty}
                className="rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-accent-fg transition-opacity hover:opacity-90 disabled:opacity-40"
              >
                {saving ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            <NodeEditor template={template} selection={selection} onChange={change} onDelete={remove} />
          </div>
        </div>
      </Panel>

      <Separator />

      {/* Right: test */}
      <Panel defaultSize={30} minSize={18}>
        <div className="h-full border-l border-border bg-surface">
          <TestPanel template={template} selection={selection} />
        </div>
      </Panel>
    </Group>
  );
}
