import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "岁实 · 投资总览",
  description: "看见积累，守住底气，让每一笔投入长成自己的树。",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
