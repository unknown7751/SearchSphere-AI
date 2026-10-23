"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { CheckCircle2, Circle, FileText, Loader2, Search, Upload, XCircle } from "lucide-react";
import Badge from "@/components/ui/Badge";
import Button, { ButtonLink } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { TextField } from "@/components/ui/Field";
import KeyValue from "@/components/ui/KeyValue";
import { ErrorState, Notice } from "@/components/ui/States";
import { uploadDocument } from "@/lib/api";
import { ACCEPTED_UPLOAD_EXTENSIONS, MAX_UPLOAD_BYTES } from "@/lib/constants";
import { formatBytes, formatNumber } from "@/lib/formatters";
import { searchHref } from "@/lib/searchUrl";

export function validateFile(file) {
  if (!file) return "Choose a .txt or .pdf file first.";
  const name = file.name.toLowerCase();
  if (!ACCEPTED_UPLOAD_EXTENSIONS.some((ext) => name.endsWith(ext))) return "Only .txt and .pdf files are supported.";
  if (file.size === 0) return "The selected file is empty.";
  if (file.size > MAX_UPLOAD_BYTES) return `The file is ${formatBytes(file.size)}; the limit is ${formatBytes(MAX_UPLOAD_BYTES)}.`;
  return null;
}

const STEPS = [
  { id: "selected", label: "File selected" },
  { id: "uploading", label: "Uploading" },
  { id: "processing", label: "Extracting text and indexing" },
  { id: "done", label: "Processed and indexed" },
];

function stepState(phase, stepId, failed) {
  const order = STEPS.map((s) => s.id);
  const current = order.indexOf(phase);
  const idx = order.indexOf(stepId);
  if (failed && idx === current) return "failed";
  if (idx < current || phase === "done") return "complete";
  if (idx === current) return "active";
  return "pending";
}

function StepList({ phase, failed }) {
  return (
    <ol className="space-y-2" aria-label="Ingestion progress">
      {STEPS.map((step) => {
        const state = stepState(phase, step.id, failed);
        const Icon = state === "complete" ? CheckCircle2 : state === "failed" ? XCircle : state === "active" ? Loader2 : Circle;
        const color =
          state === "complete" ? "text-green-700" : state === "failed" ? "text-red-700" : state === "active" ? "text-teal-700" : "text-mute-light";
        return (
          <li key={step.id} className="flex items-center gap-2 text-sm" aria-current={state === "active" ? "step" : undefined}>
            <Icon className={`h-4 w-4 ${color} ${state === "active" ? "animate-spin" : ""}`} aria-hidden="true" />
            <span className={state === "pending" ? "text-mute" : "text-ink"}>{step.label}</span>
          </li>
        );
      })}
    </ol>
  );
}

export default function IngestPanel() {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("Uploaded");
  const [fileError, setFileError] = useState(null);
  const [phase, setPhase] = useState("idle");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [uploads, setUploads] = useState([]);

  const busy = phase === "uploading" || phase === "processing";

  const onFileChange = (event) => {
    const chosen = event.target.files?.[0] || null;
    setFile(chosen);
    setFileError(chosen ? validateFile(chosen) : null);
    setResult(null);
    setError(null);
    setPhase(chosen ? "selected" : "idle");
    setProgress(0);
  };

  const submit = async (event) => {
    event.preventDefault();
    const problem = validateFile(file);
    if (problem) {
      setFileError(problem);
      return;
    }
    setError(null);
    setResult(null);
    setPhase("uploading");
    setProgress(0);
    try {
      const response = await uploadDocument(file, {
        title,
        category,
        onProgress: (fraction) => {
          setProgress(fraction);
          if (fraction >= 1) setPhase("processing");
        },
      });
      setResult(response);
      setPhase("done");
      setUploads((prev) => [{ ...response, fileName: file.name }, ...prev].slice(0, 10));
    } catch (err) {
      setError(err);
    }
  };

  const failed = Boolean(error);
  const shownPhase = phase === "idle" ? "selected" : phase;

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <Card>
        <CardHeader title="Upload a document" description="TXT and PDF files are extracted, normalised, preprocessed and added to the inverted index." icon={Upload} />
        <CardBody>
          <form onSubmit={submit} className="space-y-4" noValidate>
            <div>
              <label htmlFor="file-input" className="mb-1 block text-sm font-medium text-ink-soft">
                File
              </label>
              <input
                ref={inputRef}
                id="file-input"
                type="file"
                accept=".txt,.pdf,text/plain,application/pdf"
                onChange={onFileChange}
                disabled={busy}
                aria-invalid={fileError ? "true" : undefined}
                aria-describedby="file-help"
                className="block w-full cursor-pointer rounded border border-dashed border-mute-light bg-paper px-3 py-6 text-sm file:mr-4 file:cursor-pointer file:rounded file:border file:border-mute-line file:bg-white file:px-3 file:py-1.5 file:text-sm file:font-medium hover:border-teal-600"
              />
              <p id="file-help" className="mt-1 text-xs text-mute">
                .txt or .pdf, up to {formatBytes(MAX_UPLOAD_BYTES)}. Scanned PDFs without a text layer cannot be indexed (no OCR).
              </p>
              {fileError && (
                <p className="mt-1 text-sm text-red-700" role="alert">
                  {fileError}
                </p>
              )}
            </div>

            {file && !fileError && (
              <div className="flex items-center gap-3 rounded border border-mute-line bg-paper px-3 py-2 text-sm">
                <FileText className="h-5 w-5 shrink-0 text-teal-600" aria-hidden="true" />
                <div className="min-w-0">
                  <p className="truncate font-medium">{file.name}</p>
                  <p className="text-xs text-mute">{formatBytes(file.size)}</p>
                </div>
              </div>
            )}

            <div className="grid gap-3 sm:grid-cols-2">
              <TextField label="Title (optional)" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={300} hint="Defaults to the file name or PDF title." disabled={busy} />
              <TextField label="Category" value={category} onChange={(e) => setCategory(e.target.value)} maxLength={100} disabled={busy} />
            </div>

            <Button type="submit" variant="primary" loading={busy} disabled={!file || Boolean(fileError) || !category.trim()}>
              <Upload className="h-4 w-4" aria-hidden="true" />
              {busy ? "Working…" : "Upload and index"}
            </Button>
          </form>

          {error && <ErrorState className="mt-4" error={error} />}
        </CardBody>
      </Card>

      <div className="space-y-4">
        <Card>
          <CardHeader title="Status" />
          <CardBody className="space-y-4">
            {phase === "idle" ? (
              <p className="text-sm text-mute">Select a file to begin.</p>
            ) : (
              <>
                <StepList phase={shownPhase} failed={failed} />
                {(phase === "uploading" || phase === "processing" || phase === "done") && (
                  <div>
                    <div
                      className="h-2 overflow-hidden rounded bg-paper-dark"
                      role="progressbar"
                      aria-label="Upload progress"
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={Math.round(progress * 100)}
                    >
                      <div className="h-full bg-teal-600 transition-all" style={{ width: `${Math.round(progress * 100)}%` }} />
                    </div>
                    <p className="mt-1 text-xs text-mute">
                      {phase === "processing"
                        ? "Uploaded. The server is extracting text and updating the index in this request."
                        : `${Math.round(progress * 100)}% uploaded`}
                    </p>
                  </div>
                )}
              </>
            )}
          </CardBody>
        </Card>

        {result && (
          <Card>
            <CardHeader title="Document indexed" actions={<Badge tone="green">Indexed</Badge>} />
            <CardBody className="space-y-4">
              <KeyValue
                items={[
                  { label: "Document ID", value: <span className="font-mono">{result.document_id}</span> },
                  { label: "Title", value: result.title },
                  { label: "File type", value: result.file_type?.toUpperCase() },
                  { label: "Category", value: result.category },
                  { label: "Words", value: formatNumber(result.word_count) },
                  { label: "Index tokens", value: formatNumber(result.token_count) },
                  ...Object.entries(result.metadata || {}).map(([k, v]) => ({ label: k.replaceAll("_", " "), value: String(v) })),
                ]}
              />
              <Notice tone="teal">The document is searchable now; no restart or rebuild is needed.</Notice>
              <div className="flex flex-wrap gap-2">
                <ButtonLink href={`/documents?id=${result.document_id}`} size="sm">
                  View document
                </ButtonLink>
                <ButtonLink href={searchHref(result.title, "ranked")} size="sm" variant="primary">
                  <Search className="h-4 w-4" aria-hidden="true" />
                  Search this document
                </ButtonLink>
              </div>
            </CardBody>
          </Card>
        )}
      </div>

      {uploads.length > 1 && (
        <Card className="lg:col-span-2">
          <CardHeader title="Uploaded in this session" />
          <ul className="divide-y divide-mute-line">
            {uploads.map((u) => (
              <li key={u.document_id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2 text-sm">
                <span className="min-w-0 truncate">{u.fileName}</span>
                <Link className="font-mono text-teal-700 hover:underline" href={`/documents?id=${u.document_id}`}>
                  ID {u.document_id}
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
