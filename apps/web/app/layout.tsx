import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Zumi",
  description: "Read comics together in XR. Sketch it, Zumi inks it, voices it, and puts it in your room.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="paper" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
