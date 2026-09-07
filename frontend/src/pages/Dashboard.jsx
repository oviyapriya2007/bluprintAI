import { useState } from "react";

import StatsCards from "../components/StatsCards";
import BlueprintViewer from "../components/BlueprintViewer";
import BomTable from "../components/BomTable";
import PartDetails from "../components/PartDetails";

import { mockBlueprintData } from "../data/mockBlueprintData";

function Dashboard() {
  const [selectedPart, setSelectedPart] = useState(null);

  const { blueprint, stats, parts } = mockBlueprintData;

  return (
    <div className="dashboard">

      <header className="dashboard-header">
        <div>
          <h1>Blueprint Analysis</h1>
          <p>{blueprint.name}</p>
        </div>

        <button className="export-button">
          ↓ Export BOM
        </button>
      </header>

      <StatsCards stats={stats} />

<div className="dashboard-content">
  <BlueprintViewer
    blueprint={blueprint}
    selectedPart={selectedPart}
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

    </div>
  );
}

export default Dashboard;