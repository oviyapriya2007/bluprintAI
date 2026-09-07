export const mockBlueprintData = {
  blueprint: {
    name: "engine_assembly.pdf",
    imageUrl: "/blueprint-demo.png",
  },

  stats: {
    total: 47,
    matched: 43,
    warnings: 2,
    missing: 2,
  },

  parts: [
  {
    id: 1,
    bubble_number: "1",
    part_name: "M8 Hex Bolt",
    quantity: 4,
    material_specification: "Grade 8.8 Carbon Steel",
    confidence_score: 0.98,
    status: "matched",
    bounding_box: {
      xmin: 250,
      ymin: 120,
      xmax: 290,
      ymax: 160,
    },
  },

  {
    id: 2,
    bubble_number: "2",
    part_name: "Mounting Bracket",
    quantity: 2,
    material_specification: "Stainless Steel",
    confidence_score: 0.94,
    status: "warning",
    bounding_box: {
      xmin: 500,
      ymin: 300,
      xmax: 550,
      ymax: 350,
    },
  },

  {
    id: 3,
    bubble_number: "3",
    part_name: "Drive Shaft",
    quantity: 1,
    material_specification: "Alloy Steel",
    confidence_score: 0.97,
    status: "matched",
    bounding_box: {
      xmin: 350,
      ymin: 180,
      xmax: 410,
      ymax: 230,
    },
  },

  {
    id: 4,
    bubble_number: "4",
    part_name: "Bearing Housing",
    quantity: 2,
    material_specification: "Cast Iron",
    confidence_score: 0.91,
    status: "warning",
    bounding_box: {
      xmin: 600,
      ymin: 200,
      xmax: 660,
      ymax: 260,
    },
  },

  {
    id: 5,
    bubble_number: "5",
    part_name: "Retaining Ring",
    quantity: 2,
    material_specification: "Spring Steel",
    confidence_score: 0.96,
    status: "matched",
    bounding_box: {
      xmin: 420,
      ymin: 400,
      xmax: 460,
      ymax: 440,
    },
  },

  {
    id: 6,
    bubble_number: "6",
    part_name: "Spacer Washer",
    quantity: 4,
    material_specification: "Stainless Steel",
    confidence_score: 0.93,
    status: "matched",
    bounding_box: {
      xmin: 180,
      ymin: 350,
      xmax: 220,
      ymax: 390,
    },
  },
],
};