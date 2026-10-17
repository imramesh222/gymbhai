import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { BarChart } from "./BarChart";
import { Heatmap } from "./Heatmap";
import { LineChart } from "./LineChart";

const money = (paisa: number) => `Rs ${(paisa / 100).toLocaleString("en-IN")}`;

describe("BarChart", () => {
  const props = {
    title: "Income by month",
    labels: ["Shrawan", "Bhadra", "Asoj"],
    series: [{ key: "income", label: "Income", values: [1200_00, 1800_00, 900_00] }],
    format: money,
  };

  it("says every value to a screen reader, one column at a time", () => {
    render(<BarChart {...props} />);
    expect(screen.getByRole("img", { name: "Bhadra: Rs 1,800" })).toBeInTheDocument();
    // Only the tallest carries a label on the chart itself.
    expect(screen.getAllByText("Rs 1,800")).toHaveLength(1);
  });

  it("has the same numbers as a table", async () => {
    const user = userEvent.setup();
    render(<BarChart {...props} />);
    await user.click(screen.getByRole("button", { name: "Show as a table" }));
    const table = screen.getByRole("table");
    expect(table).toHaveTextContent("ShrawanRs 1,200");
    expect(table).toHaveTextContent("AsojRs 900");
  });

  it("shows the value when a column is focused", async () => {
    const user = userEvent.setup();
    render(<BarChart {...props} />);
    await user.tab();
    expect(screen.getByRole("presentation")).toHaveTextContent("Rs 1,200Shrawan");
  });

  it("keys two series with a legend", () => {
    render(
      <BarChart
        {...props}
        series={[
          { key: "new", label: "New", values: [3, 4, 5] },
          { key: "lapsed", label: "Lapsed", values: [1, 2, 0] },
        ]}
        format={String}
      />,
    );
    expect(screen.getByText("New")).toBeInTheDocument();
    expect(screen.getByText("Lapsed")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Asoj Lapsed: 0" })).toBeInTheDocument();
  });
});

describe("LineChart", () => {
  it("reads out every series at a point, moving with the arrow keys", async () => {
    const user = userEvent.setup();
    render(
      <LineChart
        title="Active members"
        labels={["Shrawan", "Bhadra", "Asoj"]}
        series={[{ key: "active", label: "Active", values: [null, 40, 52] }]}
      />,
    );
    const chart = screen.getByRole("img", { name: "Active members" });
    await user.click(chart);
    chart.focus();
    expect(screen.getByRole("presentation")).toHaveTextContent("Asoj52Active");
    await user.keyboard("{ArrowLeft}{ArrowLeft}");
    expect(screen.getByRole("presentation")).toHaveTextContent("Shrawan—Active");
  });
});

describe("Heatmap", () => {
  it("has every cell in its table", async () => {
    const user = userEvent.setup();
    render(
      <Heatmap
        title="Busy hours"
        rows={["Sun", "Mon"]}
        columns={["6", "7"]}
        values={[
          [0, 4],
          [9, 2],
        ]}
        format={(v) => `${v} visits`}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Show as a table" }));
    expect(screen.getByRole("table")).toHaveTextContent("Mon92");
  });
});
