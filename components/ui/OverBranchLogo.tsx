"use client";

import React from "react";

interface LogoProps {
  size?: "sm" | "md" | "lg" | "xl" | number;
  variant?: "full" | "icon" | "text";
  transparent?: boolean;
  className?: string;
  textClassName?: string;
  iconClassName?: string;
  animated?: boolean;
  colored?: boolean;
  showBeta?: boolean;
}

export function OverBranchLogo({
  size = "md",
  variant = "full",
  transparent = true,
  className = "",
  textClassName = "",
  iconClassName = "",
  animated = true,
  colored = true,
  showBeta = false,
}: LogoProps) {
  const reactId = React.useId ? React.useId().replace(/:/g, "") : "obLogo";
  const gradientId = `obLogoGrad_${reactId}`;

  const pixelSize =
    typeof size === "number"
      ? size
      : size === "sm"
      ? 24
      : size === "md"
      ? 32
      : size === "lg"
      ? 40
      : 48;

  const showIcon = variant === "full" || variant === "icon";
  const showText = variant === "full" || variant === "text";

  const strokeColor = colored ? `url(#${gradientId})` : "currentColor";
  const fillColor = colored ? `url(#${gradientId})` : "currentColor";

  return (
    <div className={`inline-flex items-center gap-2.5 select-none ${className}`}>
      {showIcon && (
        <div
          className={`relative shrink-0 flex items-center justify-center ${
            animated ? "hover:scale-105 transition-transform duration-300" : ""
          } ${iconClassName}`}
          style={{ width: pixelSize, height: pixelSize }}
        >
          <svg
            width={pixelSize}
            height={pixelSize}
            viewBox="0 0 36 36"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            className="w-full h-full text-foreground"
          >
            <defs>
              <linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#00CC68" />
                <stop offset="60%" stopColor="#00E676" />
                <stop offset="100%" stopColor="#00B359" />
              </linearGradient>
            </defs>

            {/* Main Document Body Contour */}
            <path
              d="M10 6C10 4.89543 10.8954 4 12 4H22L27 9V30C27 31.1046 26.1046 32 25 32H12C10.8954 32 10 31.1046 10 30V6Z"
              stroke={strokeColor}
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />

            {/* Folded Corner */}
            <path
              d="M22 4V9H27"
              stroke={strokeColor}
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />

            {/* Central Branching Nodes (OverBranch) */}
            <path
              d="M18 27V15"
              stroke={strokeColor}
              strokeWidth="2.5"
              strokeLinecap="round"
            />
            <path
              d="M18 22L13 17"
              stroke={strokeColor}
              strokeWidth="2.5"
              strokeLinecap="round"
            />
            <path
              d="M18 22L23 17"
              stroke={strokeColor}
              strokeWidth="2.5"
              strokeLinecap="round"
            />

            {/* Node Dots */}
            <circle cx="18" cy="27" r="2.2" fill={fillColor} />
            <circle cx="13" cy="17" r="2.2" fill={fillColor} />
            <circle cx="23" cy="17" r="2.2" fill={fillColor} />
            <circle cx="18" cy="15" r="2.2" fill={fillColor} />
          </svg>
        </div>
      )}

      {showText && (
        <span className="flex items-center gap-1.5 shrink-0">
          <span
            className={`font-archivo font-black uppercase tracking-[-0.04em] text-foreground ${
              size === "sm"
                ? "text-sm"
                : size === "md"
                ? "text-base sm:text-lg"
                : size === "lg"
                ? "text-xl"
                : "text-2xl"
            } ${textClassName}`}
          >
            OverBranch
          </span>
          {showBeta && (
            <span className="text-[9px] font-mono font-black uppercase px-1.5 py-0.2 rounded bg-zinc-800 text-[#00CC68] border border-zinc-700 tracking-wider">
              BETA
            </span>
          )}
        </span>
      )}
    </div>
  );
}
