import { useEffect, useRef, useState } from 'react';

interface Props {
  /** The full text that is currently known (grows as SSE pushes deltas). */
  text: string;
  /** True while the stream is still receiving deltas. */
  streaming: boolean;
  /** Characters revealed per second while streaming. */
  charsPerSecond?: number;
  className?: string;
}

/**
 * Typewriter that reveals the growing `text` prop char-by-char with a blinking
 * caret while `streaming` is true.
 *
 * Perf notes
 * -----------
 * - The rAF chain is set up ONCE when streaming flips true and torn down ONCE
 *   when it flips false. While streaming, the loop reads `text` from a ref,
 *   so the chain is never re-created as deltas arrive.
 * - `shown` is the only React state we set, and it's a number — React
 *   re-renders only the typewriter subtree.
 * - When the stream finishes, we snap to the final text length so the user
 *   never sees a stuck caret.
 */
export function Typewriter({ text, streaming, charsPerSecond = 48, className }: Props) {
  const [shown, setShown] = useState(0);
  // Refs for the rAF loop; never trigger re-renders or re-effects.
  const textRef = useRef(text);
  const rateRef = useRef(charsPerSecond);
  const shownRef = useRef(0);
  const lastTickRef = useRef(0);
  const rafRef = useRef<number | null>(null);

  // Mirror props into refs on every render. No re-render, no re-effect.
  textRef.current = text;
  rateRef.current = charsPerSecond;
  shownRef.current = shown;

  // Effect runs ONLY when `streaming` flips. `text` is read from textRef.
  useEffect(() => {
    if (!streaming) {
      const target = textRef.current.length;
      if (shownRef.current !== target) {
        shownRef.current = target;
        setShown(target);
      }
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      lastTickRef.current = 0;
      return undefined;
    }

    // Already running.
    if (rafRef.current != null) return undefined;

    const step = (timestamp: number) => {
      const target = textRef.current.length;
      if (shownRef.current >= target) {
        rafRef.current = null;
        return;
      }
      if (!lastTickRef.current) lastTickRef.current = timestamp;
      const elapsed = (timestamp - lastTickRef.current) / 1000;
      const revealCount = Math.max(1, Math.floor(elapsed * rateRef.current));
      const next = Math.min(target, shownRef.current + revealCount);
      shownRef.current = next;
      setShown(next);
      if (next >= target) {
        lastTickRef.current = 0;
        rafRef.current = null;
        return;
      }
      lastTickRef.current = timestamp;
      rafRef.current = requestAnimationFrame(step);
    };

    lastTickRef.current = 0;
    rafRef.current = requestAnimationFrame(step);

    return () => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      lastTickRef.current = 0;
    };
  }, [streaming]);

  const visible = text.slice(0, shown);
  const showCaret = streaming && shown < text.length;

  return (
    <div className={className ? `typewriter ${className}` : 'typewriter'}>
      {visible}
      {showCaret ? <span className="caret" aria-hidden /> : null}
    </div>
  );
}
