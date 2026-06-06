"use client";

import type { GlyphTemplate, JobStep } from "@/lib/types";
import { clone, type Selection } from "@/lib/glyph";
import { Field, NumberInput, Select, TextInput } from "./fields";
import { StepList } from "./StepList";

export function NodeEditor({
  template,
  selection,
  onChange,
  onDelete,
}: {
  template: GlyphTemplate;
  selection: Selection;
  onChange: (t: GlyphTemplate) => void;
  onDelete: (s: Selection) => void;
}) {
  const update = (mut: (t: GlyphTemplate) => void) => {
    const next = clone(template);
    mut(next);
    onChange(next);
  };

  if (selection.kind === "root") {
    return (
      <Panel title="Template" subtitle="Top-level glyph settings">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Model">
            <TextInput value={template.model} onChange={(e) => update((t) => (t.model = e.target.value))} />
          </Field>
          <Field label="Symbol">
            <TextInput value={template.symbol} onChange={(e) => update((t) => (t.symbol = e.target.value))} />
          </Field>
          <Field label="Interval">
            <TextInput value={template.interval} onChange={(e) => update((t) => (t.interval = e.target.value))} />
          </Field>
          <Field label="Space">
            <Select value={template.space} onChange={(e) => update((t) => (t.space = e.target.value))}>
              <option value="bipolar">bipolar</option>
              <option value="binary">binary</option>
            </Select>
          </Field>
          <Field label="Dimension">
            <NumberInput value={template.dim} onChange={(e) => update((t) => (t.dim = Number(e.target.value)))} />
          </Field>
        </div>
      </Panel>
    );
  }

  if (selection.kind === "layer") {
    const layer = template.layers[selection.l];
    if (!layer) return <Empty />;
    return (
      <Panel title={`Layer · ${layer.key}`} subtitle="Composited into the cortex" onDelete={() => onDelete(selection)}>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Key">
            <TextInput value={layer.key} onChange={(e) => update((t) => (t.layers[selection.l].key = e.target.value))} />
          </Field>
          <Field label="Weight">
            <NumberInput step="0.1" value={layer.weight} onChange={(e) => update((t) => (t.layers[selection.l].weight = Number(e.target.value)))} />
          </Field>
          <Field label="Execution">
            <Select value={layer.execution} onChange={(e) => update((t) => (t.layers[selection.l].execution = e.target.value as "sequential" | "parallel"))}>
              <option value="sequential">sequential</option>
              <option value="parallel">parallel</option>
            </Select>
          </Field>
        </div>
        <p className="mt-3 text-xs text-text-muted">{layer.segments.length} segment(s)</p>
      </Panel>
    );
  }

  if (selection.kind === "segment") {
    const seg = template.layers[selection.l]?.segments[selection.s];
    if (!seg) return <Empty />;
    return (
      <Panel title={`Segment · ${seg.key}`} subtitle="Roles + the job that fills them" onDelete={() => onDelete(selection)}>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Key">
            <TextInput value={seg.key} onChange={(e) => update((t) => (t.layers[selection.l].segments[selection.s].key = e.target.value))} />
          </Field>
          <Field label="Weight">
            <NumberInput step="0.1" value={seg.weight} onChange={(e) => update((t) => (t.layers[selection.l].segments[selection.s].weight = Number(e.target.value)))} />
          </Field>
        </div>
        <div className="mt-4">
          <span className="mb-2 block text-[11px] font-semibold uppercase tracking-wider text-text-muted">
            Job steps
          </span>
          <StepList
            job={seg.job}
            roles={seg.roles}
            onChange={(job: JobStep[]) =>
              update((t) => (t.layers[selection.l].segments[selection.s].job = job))
            }
          />
        </div>
      </Panel>
    );
  }

  // role
  const role = template.layers[selection.l]?.segments[selection.s]?.roles[selection.r];
  if (!role) return <Empty />;
  return (
    <Panel title={`Role · ${role.key}`} subtitle="A key/value bound into the segment vector" onDelete={() => onDelete(selection)}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Key">
          <TextInput value={role.key} onChange={(e) => update((t) => (t.layers[selection.l].segments[selection.s].roles[selection.r].key = e.target.value))} />
        </Field>
        <Field label="Type">
          <Select value={role.type} onChange={(e) => update((t) => (t.layers[selection.l].segments[selection.s].roles[selection.r].type = e.target.value as "scalar" | "symbol"))}>
            <option value="scalar">scalar</option>
            <option value="symbol">symbol</option>
          </Select>
        </Field>
        <Field label="Weight">
          <NumberInput step="0.1" value={role.weight} onChange={(e) => update((t) => (t.layers[selection.l].segments[selection.s].roles[selection.r].weight = Number(e.target.value)))} />
        </Field>
        {role.type === "scalar" && (
          <>
            <Field label="Range min">
              <NumberInput
                value={role.range?.[0] ?? 0}
                onChange={(e) => update((t) => {
                  const r = t.layers[selection.l].segments[selection.s].roles[selection.r];
                  r.range = [Number(e.target.value), r.range?.[1] ?? 0];
                })}
              />
            </Field>
            <Field label="Range max">
              <NumberInput
                value={role.range?.[1] ?? 0}
                onChange={(e) => update((t) => {
                  const r = t.layers[selection.l].segments[selection.s].roles[selection.r];
                  r.range = [r.range?.[0] ?? 0, Number(e.target.value)];
                })}
              />
            </Field>
          </>
        )}
      </div>
    </Panel>
  );
}

function Panel({
  title,
  subtitle,
  onDelete,
  children,
}: {
  title: string;
  subtitle: string;
  onDelete?: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col">
      <div className="mb-4 flex items-start justify-between">
        <div>
          <h2 className="text-sm font-semibold">{title}</h2>
          <p className="text-xs text-text-muted">{subtitle}</p>
        </div>
        {onDelete && (
          <button
            onClick={onDelete}
            className="rounded-md border border-border px-2 py-1 text-xs font-medium text-bad transition-colors hover:border-bad"
          >
            Delete
          </button>
        )}
      </div>
      {children}
    </div>
  );
}

function Empty() {
  return <p className="text-sm text-text-muted">Node no longer exists.</p>;
}
