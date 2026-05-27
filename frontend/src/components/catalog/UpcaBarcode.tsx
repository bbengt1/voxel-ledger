/**
 * UPC-A barcode rendered inline as SVG.
 *
 * UPC-A encodes 12 digits as a fixed-width pattern of bars and spaces:
 *
 *   Start guard (101)
 *   6 left digits, each a 7-bit "L" code (odd-parity)
 *   Center guard (01010)
 *   6 right digits, each a 7-bit "R" code (even-parity)
 *   End guard (101)
 *
 * Total: 95 modules wide. Each module is rendered as a 1×height rect
 * at integer coordinates, so any browser-side rasterisation hits
 * sharp pixel boundaries. The 12th digit is the standard mod-10
 * check digit — callers are expected to pass a complete 12-digit
 * code (the products endpoint's UPC generator already does so).
 */
import { useMemo } from "react";

const L_CODES: Record<string, string> = {
  "0": "0001101",
  "1": "0011001",
  "2": "0010011",
  "3": "0111101",
  "4": "0100011",
  "5": "0110001",
  "6": "0101111",
  "7": "0111011",
  "8": "0110111",
  "9": "0001011",
};

// R-codes are the bitwise complement of L-codes.
const R_CODES: Record<string, string> = Object.fromEntries(
  Object.entries(L_CODES).map(([d, bits]) => [
    d,
    bits.replace(/[01]/g, (c) => (c === "0" ? "1" : "0")),
  ]),
);

const START = "101";
const CENTER = "01010";
const END = "101";

function encode(upc: string): string {
  const left = upc.slice(0, 6);
  const right = upc.slice(6, 12);
  return (
    START +
    left
      .split("")
      .map((d) => L_CODES[d] ?? "0000000")
      .join("") +
    CENTER +
    right
      .split("")
      .map((d) => R_CODES[d] ?? "0000000")
      .join("") +
    END
  );
}

interface Props {
  /** Exactly 12 numeric digits. */
  value: string;
  /** Height of the bar area in CSS pixels. Defaults to 32. */
  height?: number;
  /** Whether to render the human-readable digit line beneath the bars. */
  showDigits?: boolean;
  className?: string;
}

export function UpcaBarcode({
  value,
  height = 32,
  showDigits = true,
  className,
}: Props) {
  const sanitized = useMemo(
    () => (value || "").replace(/\D/g, "").padStart(12, "0").slice(-12),
    [value],
  );
  const bits = useMemo(() => encode(sanitized), [sanitized]);
  const modules = 95; // total module count
  // Pad the viewBox horizontally so the outer-digit readout characters
  // ("2" on the far left, "4" on the far right of a UPC) have room to
  // render inside the SVG instead of overflowing into the next label.
  const padX = 6;
  const width = modules + padX * 2;
  const textY = height + 10;
  const viewBoxHeight = showDigits ? height + 14 : height;

  // Collapse runs of "1" bits into rect elements for fewer SVG nodes.
  const rects: { x: number; w: number }[] = [];
  let i = 0;
  while (i < bits.length) {
    if (bits[i] === "1") {
      let j = i;
      while (j < bits.length && bits[j] === "1") j++;
      rects.push({ x: i, w: j - i });
      i = j;
    } else {
      i++;
    }
  }

  // Split digits for the readout: first digit far-left, 5 + 5 across
  // the bottom centered under their bars, last digit far-right.
  const left5 = sanitized.slice(1, 6);
  const right5 = sanitized.slice(6, 11);

  return (
    <svg
      className={className}
      viewBox={`0 0 ${width} ${viewBoxHeight}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={`Barcode ${sanitized}`}
      shapeRendering="crispEdges"
      style={{ overflow: "hidden" }}
    >
      <rect x={0} y={0} width={width} height={viewBoxHeight} fill="white" />
      {/* Bars start at ``padX`` so the outer digits have a gutter. */}
      {rects.map((r, idx) => (
        <rect
          key={idx}
          x={r.x + padX}
          y={0}
          width={r.w}
          height={height}
          fill="black"
        />
      ))}
      {showDigits ? (
        <g
          fill="black"
          fontFamily="ui-monospace, SFMono-Regular, monospace"
          fontSize={9}
          textAnchor="middle"
        >
          <text x={padX / 2} y={textY}>
            {sanitized[0]}
          </text>
          <text x={padX + 20} y={textY}>
            {left5}
          </text>
          <text x={padX + 67} y={textY}>
            {right5}
          </text>
          <text x={padX + modules + padX / 2} y={textY}>
            {sanitized[11]}
          </text>
        </g>
      ) : null}
    </svg>
  );
}
