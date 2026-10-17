import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../lib/cn";

const button = cva(
  "inline-flex items-center justify-center gap-2 select-none whitespace-nowrap transition-colors duration-fast ease-standard focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-50 disabled:pointer-events-none",
  {
    variants: {
      variant: {
        /** Lamp amber with dark ink: Enter, Join, Creator's. The only loud control. */
        cta: "bg-cta text-text-on-cta hover:bg-cta-hover font-display font-extrabold uppercase tracking-[0.05em] rounded-control",
        /** Brown accent fill, white text. Secondary actions. */
        accent: "bg-accent text-text-on-accent hover:opacity-90 font-body font-bold rounded-control",
        /** Hairline outline, dim text. Log in, cancel. */
        ghost: "bg-transparent text-text-dim border border-hairline-strong hover:text-text-default hover:border-text-dim font-body rounded-control",
        /** Text only, accent colour. "See all", inline links. */
        link: "bg-transparent text-accent hover:underline underline-offset-2 font-body p-0 h-auto",
      },
      size: {
        sm: "h-7 px-3 text-sm",
        md: "h-9 px-4 text-md",
        lg: "h-11 px-5 text-lg",
      },
    },
    compoundVariants: [{ variant: "cta", size: "md", class: "text-lg" }],
    defaultVariants: { variant: "accent", size: "md" },
  },
);

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof button> {
  /** Render the child element instead of a <button> (for links). */
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant, size, asChild, type = "button", ...props },
  ref,
) {
  const Comp = asChild ? Slot : "button";
  return <Comp ref={ref} type={asChild ? undefined : type} className={cn(button({ variant, size }), className)} {...props} />;
});
