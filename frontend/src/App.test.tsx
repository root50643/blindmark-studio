import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { App } from "./App";

vi.mock("./api/client", () => ({
  api: {
    capabilities: vi.fn().mockResolvedValue({}),
  },
}));

test("renders the public watermark workspace", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: /看不見的標記/ })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "嵌入浮水印" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "解碼浮水印" })).toBeInTheDocument();
});
