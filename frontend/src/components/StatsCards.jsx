function StatsCards({ stats }) {
  const cards = [
    {
      label: "Total Parts",
      value: stats.total,
    },
    {
      label: "Matched",
      value: stats.matched,
    },
    {
      label: "Warnings",
      value: stats.warnings,
    },
    {
      label: "Missing",
      value: stats.missing,
    },
  ];

  return (
    <div className="stats-grid">
      {cards.map((card) => (
        <div className="stat-card" key={card.label}>
          <div className="stat-value">{card.value}</div>
          <div className="stat-label">{card.label}</div>
        </div>
      ))}
    </div>
  );
}

export default StatsCards;