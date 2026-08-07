"use client";

import { motion } from "framer-motion";
import { OverBranchLogo } from "@/components/ui/OverBranchLogo";

export function LoadingScreen({ message = "Initializing OverBranch..." }: { message?: string }) {
  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-background/95 backdrop-blur-xl">
      <div className="relative flex flex-col items-center">
        <div className="absolute -inset-4 rounded-full bg-gradient-to-r from-indigo-500/20 via-cyan-500/20 to-purple-500/20 blur-xl animate-pulse" />
        
        <motion.div
          initial={{ scale: 0.9, opacity: 0.8 }}
          animate={{ scale: 1.05, opacity: 1 }}
          transition={{ duration: 1.2, repeat: Infinity, repeatType: "reverse" }}
          className="relative flex items-center justify-center"
        >
          <OverBranchLogo size={64} variant="icon" colored animated={false} />
        </motion.div>

        <h2 className="mt-6 text-xl font-extrabold tracking-tight text-foreground">
          OverBranch
        </h2>
        <p className="mt-2 text-sm text-muted-foreground animate-pulse font-mono">
          {message}
        </p>

        <div className="w-48 h-1 mt-6 rounded-full bg-muted overflow-hidden relative">
          <motion.div
            className="absolute left-0 top-0 bottom-0 bg-gradient-to-r from-indigo-500 via-cyan-400 to-purple-500"
            initial={{ left: "-100%", right: "100%" }}
            animate={{ left: "100%", right: "-100%" }}
            transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
          />
        </div>
      </div>
    </div>
  );
}
