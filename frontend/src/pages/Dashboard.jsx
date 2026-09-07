import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import StatsCards from "../components/StatsCards";
import BlueprintViewer from "../components/BlueprintViewer";
import BomTable from "../components/BomTable";
import PartDetails from "../components/PartDetails";
import ValidationPanel from "../components/ValidationPanel";
import ProcurementPanel from "../components/ProcurementPanel";
import { exportWorkspace, BlueprintApiError } from "../api/blueprintApi";
import { adaptWorkspaceToParts, computeStats, flattenValidationIssues } from "../utils/adaptWorkspace";

/** Recover the real backend result from router state, or (on a page
 * refresh, which loses router state) from the sessionStorage copy saved
 * right after a successful upload. The uploaded-drawing image itself is a
 * blob: URL and cannot survive a reload -- that's a known, honest gap for
 * a client-only SPA with no server-side session. */
function useWorkspaceData() {
  const location = useLocation();

  return useMemo(() => {
    if (location.state?.workspace) {
      return {
        workspace: location.state.workspace,
        imageUrl: location.state.imageUrl ?? null,
        fileName: location.state.fileName ?? "drawing",
        fileType: location.state.fileType ?? null,
      };
    }

    try {
      const stored = sessionStorage.getItem("blueprintai_workspace");
      if (stored) {
        return {
          workspace: JSON.parse(stored),
          imageUrl: null,
          fileName: sessionStorage.getItem("blueprintai_filename") || "drawing",
          fileType: null,
        };
      }
    } catch {
      /* ignore -- fall through to null */
    }

    return null;
  }, [location.state]);
}

function Dashboard() {
  const navigate = useNavigate();
  const data = useWorkspaceData();
  const [selectedPart, setSelectedPart] = useState(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState(null);

  useEffect(() => {
    if (!data) navigate("/", { replace: true });
  }, [data, navigate]);

  if (!data) {
    return null; // redirecting
  }

  const { workspace, imageUrl, fileName, fileType } = data;
  const parts = adaptWorkspaceToParts(workspace);
  const stats = computeStats(workspace);
  const issues = flattenValidationIssues(workspace);
  const metadata = workspace.metadata || {};
  const isDegraded = metadata.pipeline_status && metadata.pipeline_status !== "ok";

  const handleExport = async () => {
    setExporting(true);
    setExportError(null);
    try {
      const blob = await exportWorkspace(workspace);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "BlueprintAI_BOM.xlsx";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(err instanceof BlueprintApiError ? err.message : "Export failed.");
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="dashboard">

      <header className="dashboard-header">
        <div>
          <h1>Blueprint Analysis</h1>
          <p>{fileName}</p>
        </div>

        <div className="export-buttons">
          <button
            className="export-button"
            onClick={handleExport}
            disabled={exporting}
          >
            {exporting ? "Exporting..." : "↓ Export Excel"}
          </button>
        </div>
      </header>

      {exportError && <div className="upload-error dashboard-banner">{exportError}</div>}

      {isDegraded && (
        <div className="pipeline-warning-banner">
          Processing completed with warnings ({metadata.pipeline_status}).
          {metadata.pipeline_errors?.length > 0 && (
            <ul>
              {metadata.pipeline_errors.map((err, index) => (
                <li key={index}>[{err.stage}] {err.message}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <StatsCards stats={stats} />

      <div className="dashboard-content">
        <BlueprintViewer
          blueprint={{ name: fileName, imageUrl, fileType }}
          parts={parts}
          selectedPart={selectedPart}
          onSelect={setSelectedPart}
        />

        <div>
          <BomTable
            parts={parts}
            selectedPart={selectedPart}
            onSelect={setSelectedPart}
          />

          <PartDetails part={selectedPart} />
        </div>
      </div>

      <div className="dashboard-content dashboard-content-secondary">
        <ValidationPanel issues={issues} />
        <ProcurementPanel parts={parts} summary={workspace.procurement_summary} />
      </div>

    </div>
  );
}

export default Dashboard;
