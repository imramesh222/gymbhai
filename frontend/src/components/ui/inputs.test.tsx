import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { DateInput } from "./inputs";

function Harness({ display }: { display: "ad" | "bs" | "both" }) {
  const [value, setValue] = useState("2026-09-19");
  return (
    <>
      <DateInput label="Starts" value={value} onChange={setValue} display={display} />
      <output>{value}</output>
    </>
  );
}

describe("DateInput", () => {
  it("lets a BS gym enter a BS date, and stores AD", () => {
    render(<Harness display="bs" />);
    fireEvent.change(screen.getByLabelText("BS year"), { target: { value: "2083" } });
    fireEvent.change(screen.getByLabelText("BS month"), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText("BS day"), { target: { value: "5" } });
    // 5 Baisakh 2083 is 18 April 2026 (the PLAN.md §5.1 example's start).
    expect(document.querySelector("output")).toHaveTextContent("2026-04-18");
    expect(screen.getByText("18 Apr 2026")).toBeInTheDocument();
  });

  it("keeps the day inside a shorter month", () => {
    render(<Harness display="both" />);
    fireEvent.click(screen.getByRole("button", { name: "Enter in BS" }));
    // In 2083 Asar has 32 days and Mangsir 29: the 32nd of Asar, moved to
    // Mangsir, becomes the 29th.
    fireEvent.change(screen.getByLabelText("BS month"), { target: { value: "3" } });
    fireEvent.change(screen.getByLabelText("BS day"), { target: { value: "32" } });
    fireEvent.change(screen.getByLabelText("BS month"), { target: { value: "8" } });
    expect(screen.getByLabelText("BS day")).toHaveValue("29");
  });

  it("AD gyms get a plain date input", () => {
    render(<Harness display="ad" />);
    expect(screen.queryByRole("button", { name: "Enter in BS" })).toBeNull();
    expect(screen.getByLabelText("Starts")).toHaveAttribute("type", "date");
  });
});
