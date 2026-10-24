import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { RiskBadge } from "./ui";

afterEach(() => {
  cleanup();
});

describe("RiskBadge", () => {
  it("renders an explicit N/A for a missing level (null)", () => {
    render(<RiskBadge level={null} />);
    expect(screen.getByText("N/A")).toBeTruthy();
    expect(screen.getByTitle("Risk assessment not available")).toBeTruthy();
  });

  it("renders N/A for undefined (no default fabrication of a classification)", () => {
    render(<RiskBadge />);
    expect(screen.getByText("N/A")).toBeTruthy();
  });

  it("renders known levels with their uppercase label", () => {
    render(<RiskBadge level="none" />);
    expect(screen.getByText("NONE")).toBeTruthy();
  });

  it("renders medium level", () => {
    render(<RiskBadge level="medium" />);
    expect(screen.getByText("MEDIUM")).toBeTruthy();
  });

  it("renders critical level", () => {
    render(<RiskBadge level="critical" />);
    expect(screen.getByText("CRITICAL")).toBeTruthy();
  });

  it("does not crash on an unknown non-empty level string", () => {
    render(<RiskBadge level="banana" />);
    expect(screen.getByText("BANANA")).toBeTruthy();
  });

  it("supports the lg size with missing data", () => {
    render(<RiskBadge level={null} size="lg" />);
    expect(screen.getByText("N/A")).toBeTruthy();
  });
});
