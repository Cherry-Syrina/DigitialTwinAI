import { useState } from "react";
import { Link } from "react-router-dom";
import { Download, FileDown, FileText, Printer } from "lucide-react";
import { api } from "../api";
import { useApp } from "../store";
import { DataTag, EmptyState, ErrorBanner, PageHeader, Panel, Spinner } from "../components/ui";
import MarkdownView from "../components/MarkdownView";

export default function Reports() {
  const { selectedId, patients, profile } = useApp();
  const selected = patients.find((p) => p.patient_id === selectedId);

  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState(false);
  const [pdfBusy, setPdfBusy] = useState(false);
  const [error, setError] = useState(null);

  const generate = async () => {
    if (!selectedId) return;
    setBusy(true);
    setError(null);
    try {
      setReport(await api.report(selectedId));
    } catch (err) {
      setError(err.message);
      setReport(null);
    } finally {
      setBusy(false);
    }
  };

  const downloadMarkdown = () => {
    if (!report) return;
    const blob = new Blob([report.content_markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `glucotwin-report-${report.patient_id}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const downloadPdf = async () => {
    if (!selectedId) return;
    setPdfBusy(true);
    setError(null);
    try {
      // Generated server-side so it is identical for every viewer/printer.
      const blob = await api.reportPdf(selectedId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `glucotwin-report-${selectedId}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message);
    } finally {
      setPdfBusy(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Reports"
        breadcrumb="Output"
        subtitle="Generate a printable patient report covering demographics, history, observations, forecast, risk and metrics."
        actions={
          <>
            <button className="btn-secondary" onClick={generate} disabled={busy || !selectedId}>
              <FileText className="h-4 w-4" /> {busy ? "Generating…" : "Generate report"}
            </button>
            <button
              className="btn-primary"
              onClick={downloadPdf}
              disabled={pdfBusy || !selectedId}
              data-testid="download-pdf"
            >
              <FileDown className="h-4 w-4" /> {pdfBusy ? "Preparing PDF…" : "Download PDF"}
            </button>
            <button className="btn-secondary" onClick={downloadMarkdown} disabled={!report}>
              <Download className="h-4 w-4" /> Download .md
            </button>
          <button className="btn-secondary" onClick={() => window.print()} disabled={!report}>
            <Printer className="h-4 w-4" /> Print / PDF
          </button>
          </>
        }
        meta={
          selected && (
            <>
              <span className="text-[13px] font-medium text-slate-900">{selected.name}</span>
              <span className="badge bg-slate-100 text-slate-600">{selected.patient_id}</span>
              <DataTag label={selected.data_label} />
            </>
          )
        }
      />

      {!selectedId && <div className="card"><EmptyState icon={FileText} title="No patient selected" description="Choose an existing patient or register a demonstration profile before generating a report." action={<><Link className="btn-primary" to="/patients">Choose patient</Link><Link className="btn-secondary" to="/patients/new">Add patient</Link></>} /></div>}
      {error && <ErrorBanner message={error} />}
      {busy && !report && <Spinner label="Generating report…" />}

      {report && (
        <div className="card print-area overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-2 text-[11px] text-slate-500">
            <span>
              Generated {report.generated_at ? new Date(report.generated_at).toLocaleString("en-GB", { hour12: false }) : "—"} ·
              patient {report.patient_id}
            </span>
            <span className="flex items-center gap-2">
              <DataTag label={report.data_label} />
              {profile?.name ? <span>{profile.name}</span> : null}
            </span>
          </div>
          <div className="prose-report p-4 md:p-6">
            <MarkdownView content={report.content_markdown} />
          </div>
        </div>
      )}

      {!report && !busy && selectedId && (
        <div className="card">
          <EmptyState
            icon={FileText}
            title="No report generated yet"
            description="Press Generate report in the header to create a structured, printable patient summary with demographics, observations, forecast, risk and metrics."
          />
        </div>
      )}
    </>
  );
}
