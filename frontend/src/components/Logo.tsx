import type { SVGProps } from "react";

// The document sits inside the shield so the mark reads as a protected standard.
export function Logo(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 128 128" fill="none" aria-hidden="true" {...props}>
      <path
        d="M64 12 104 28v29c0 27-16 48-40 59-24-11-40-32-40-59V28l40-16Z"
        stroke="currentColor"
        strokeWidth="7"
        strokeLinejoin="round"
      />
      <path
        d="M46 40h25l13 13v35H46V40Z"
        stroke="currentColor"
        strokeWidth="6"
        strokeLinejoin="round"
      />
      <path d="M71 40v13h13M56 66h18M56 77h15" stroke="currentColor" strokeWidth="5" />
    </svg>
  );
}
