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
}

export function OverBranchLogo({
  size = "md",
  variant = "full",
  transparent = true,
  className = "",
  textClassName = "",
  iconClassName = "",
  animated = true,
  colored = false,
}: LogoProps) {
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

  const strokeColor = colored ? "url(#obLogoGradient)" : "currentColor";
  const fillColor = colored ? "url(#obLogoGradient)" : "currentColor";

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
              <linearGradient id="obLogoGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#6366f1" />
                <stop offset="50%" stopColor="#a855f7" />
                <stop offset="100%" stopColor="#06b6d4" />
              </linearGradient>
            </defs>

            <path
              d="M13 5H21L25 9V17C25 18.1046 24.1046 19 23 19H13C11.8954 19 11 18.1046 11 17V7C11 5.89543 11.8954 5 13 5Z"
              stroke={strokeColor}
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path
              d="M21 5V9H25"
              stroke={strokeColor}
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />

            <path
              d="M18 30V19"
              stroke={strokeColor}
              strokeWidth="2.2"
              strokeLinecap="round"
            />
            <path
              d="M18 26L9 20"
              stroke={strokeColor}
              strokeWidth="2.2"
              strokeLinecap="round"
            />
            <path
              d="M18 26L27 20"
              stroke={strokeColor}
              strokeWidth="2.2"
              strokeLinecap="round"
            />

            <circle cx="18" cy="30" r="2.2" fill={fillColor} stroke={strokeColor} strokeWidth="1" />
            <circle cx="7" cy="19" r="2.2" fill={fillColor} stroke={strokeColor} strokeWidth="1" />
            <circle cx="29" cy="19" r="2.2" fill={fillColor} stroke={strokeColor} strokeWidth="1" />
          </svg>
        </div>
      )}

      {showText && (
        <span
          className={`font-extrabold tracking-tight text-foreground font-sans ${
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
      )}
    </div>
  );
}
