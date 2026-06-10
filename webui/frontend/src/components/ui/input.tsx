// Author: Dr Diego Malpica MD
import * as React from "react";
import { cn } from "@/lib/utils";

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-10 w-full rounded-[3px] border border-input bg-black/40 px-3 py-2 text-sm text-foreground ring-offset-background transition file:border-0 file:bg-transparent file:text-xs file:font-semibold file:uppercase file:tracking-[0.1em] file:text-muted-foreground placeholder:text-muted-foreground focus-visible:border-white/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/15 focus-visible:ring-offset-0 disabled:cursor-not-allowed disabled:opacity-50",
          className
        )}
        ref={ref}
        {...props}
      />
    );
  }
);
Input.displayName = "Input";

export { Input };
