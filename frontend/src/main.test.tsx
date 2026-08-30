import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import "@testing-library/jest-dom/vitest";

function Preview() {
  return <main aria-label="PD Agent preview">PD Agent v0.9</main>;
}

describe("frontend scaffold", () => {
  it("renders the product identity", () => {
    render(<Preview />);
    expect(screen.getByRole("main", { name: "PD Agent preview" })).toHaveTextContent("PD Agent v0.9");
  });
});
