"use client";

import { motion } from "framer-motion";
import { Cpu } from "lucide-react";

export function LoadingScreen({ message = "Initializing OverBranch..." }: { message?: string }) {
  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-background/95 backdrop-blur-xl">
      <div className="relative flex flex-col items-center">
        <div className="absolute -inset-4 rounded-full bg-gradient-to-r from-indigo-500/20 via-cyan-500/20 to-purple-500/20 blur-xl animate-pulse" />
        
        <motion.div
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.5, repeat: Infinity, repeatType: "reverse" }}
          className="relative w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-600 to-cyan-600 flex items-center justify-center shadow-2xl shadow-indigo-500/30"
        >
          <Cpu className="w-8 h-8 text-white" />
        </motion.div>

        <h2 className="mt-6 text-xl font-bold tracking-tight text-foreground">
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
