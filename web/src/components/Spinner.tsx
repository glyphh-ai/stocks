"use client";

import { useEffect, useState } from "react";

const FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];

/** A braille spinner that cycles glyphs in place, for inline "busy" states. */
export function Spinner({ className = "" }: { className?: string }) {
  const [i, setI] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => setI((n) => (n + 1) % FRAMES.length), 80);
    return () => window.clearInterval(id);
  }, []);
  return (
    <span aria-label="loading" className={`inline-block tabular-nums ${className}`}>
      {FRAMES[i]}
    </span>
  );
}
