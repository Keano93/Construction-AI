import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Notice",
  description: "AI commercial assistant for contractors. Agents draft, humans approve.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-IE">
      <body>{children}</body>
    </html>
  );
}
