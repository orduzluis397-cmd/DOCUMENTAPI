"use client";

import { CheckIcon, PencilIcon, TriangleAlertIcon, XIcon } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { correctField, type ExtractedField } from "@/lib/api";
import { displayValue, parseInput } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Campos extraídos: dudosos primero y resaltados; todos editables. */
export function FieldList({
  fields,
  onChange,
}: {
  fields: ExtractedField[];
  onChange: (field: ExtractedField) => void;
}) {
  const doubtful = fields.filter((f) => f.is_doubtful && f.corrected_value === null).length;
  const ordered = [...fields].sort(
    (a, b) => Number(b.is_doubtful) - Number(a.is_doubtful) || a.name.localeCompare(b.name),
  );

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-muted-foreground">
        {fields.length} campos ·{" "}
        {doubtful > 0 ? (
          <span className="font-medium text-warning-foreground">{doubtful} por revisar</span>
        ) : (
          "ninguno pendiente"
        )}
      </p>
      <ul className="flex flex-col gap-2">
        {ordered.map((f) => (
          <FieldRow key={f.id} field={f} onChange={onChange} />
        ))}
      </ul>
    </div>
  );
}

function FieldRow({
  field,
  onChange,
}: {
  field: ExtractedField;
  onChange: (field: ExtractedField) => void;
}) {
  const current = field.corrected_value ?? field.value;
  const corrected = field.corrected_value !== null;
  const pending = field.is_doubtful && !corrected;
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(displayValue(current));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      onChange(await correctField(field.id, parseInput(draft, field.value)));
      setEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <li
      className={cn(
        "rounded-lg border px-3 py-2",
        pending && "border-warning-foreground/40 bg-warning",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 font-mono text-xs">
          {pending && (
            <TriangleAlertIcon className="size-3.5 text-warning-foreground" aria-label="Dudoso" />
          )}
          {field.name}
        </span>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {corrected && <span className="font-medium">corregido</span>}
          {field.confidence !== null && (
            <span title="Confianza del extractor">{Math.round(field.confidence * 100)} %</span>
          )}
          {field.page !== null && <span>pág. {field.page}</span>}
        </div>
      </div>

      {editing ? (
        <form
          className="mt-1.5 flex items-center gap-1.5"
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
        >
          <input
            aria-label={field.name}
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") setEditing(false);
            }}
            className="h-8 flex-1 rounded-md border border-input bg-background px-2 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
          />
          <Button type="submit" size="icon-sm" disabled={saving} aria-label="Guardar">
            <CheckIcon />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label="Cancelar"
            onClick={() => {
              setEditing(false);
              setDraft(displayValue(current));
            }}
          >
            <XIcon />
          </Button>
        </form>
      ) : (
        <div className="mt-1 flex items-center justify-between gap-2">
          <span className="text-sm break-all">
            {displayValue(current) || <span className="text-muted-foreground italic">vacío</span>}
            {corrected && (
              <span className="ml-2 text-xs text-muted-foreground line-through">
                {displayValue(field.value)}
              </span>
            )}
          </span>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={`Editar ${field.name}`}
            onClick={() => {
              setDraft(displayValue(current));
              setEditing(true);
            }}
          >
            <PencilIcon />
          </Button>
        </div>
      )}
      {error && (
        <p role="alert" className="mt-1 text-xs text-destructive">
          {error}
        </p>
      )}
    </li>
  );
}
