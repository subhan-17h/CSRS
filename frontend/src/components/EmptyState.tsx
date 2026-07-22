import { useEffect, useRef, useState } from "react";

const WORD = "CSRS";

const SUGGESTIONS = [
  "What are the functions of the NIST Cybersecurity Framework?",
  "What does ISO 27001 require for access control?",
  "How is Incident Response handled?",
  "What are the requirements for Asset Management?"
];

type EmptyStateProps = {
  onPick: (prompt: string) => void;
  active: boolean;
};

export function EmptyState({ onPick, active }: EmptyStateProps) {
  const [typed, setTyped] = useState("");
  const [done, setDone] = useState(false);
  const timers = useRef<number[]>([]);

  useEffect(() => {
    timers.current.forEach(window.clearTimeout);
    timers.current = [];
    setTyped("");
    setDone(false);

    if (!active) return;

    let index = 0;
    const step = () => {
      index += 1;
      setTyped(WORD.slice(0, index));
      if (index < WORD.length) {
        timers.current.push(window.setTimeout(step, 120));
      } else {
        timers.current.push(window.setTimeout(() => setDone(true), 220));
      }
    };
    timers.current.push(window.setTimeout(step, 360));

    return () => {
      timers.current.forEach(window.clearTimeout);
      timers.current = [];
    };
  }, [active]);

  return (
    <div className="hero">
      <div className="hero-desc">Cybersecurity Standards Assistant</div>
      <div className="hero-word">
        {typed}
        <span className={"word-caret" + (done ? " idle" : "")} />
      </div>
      <div className="hero-chips">
        {SUGGESTIONS.map((suggestion) => (
          <button key={suggestion} className="suggest-chip" onClick={() => onPick(suggestion)}>
            {suggestion}
          </button>
        ))}
      </div>
    </div>
  );
}
