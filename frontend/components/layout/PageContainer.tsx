import React from "react";

interface PageContainerProps {
  children: React.ReactNode;
}

export default function PageContainer({ children }: PageContainerProps) {
  return (
    <main className="flex-1 overflow-y-auto p-6 md:p-8 space-y-6 bg-[#0a0f1d]">
      {children}
    </main>
  );
}
