import React from "react";

interface PageContainerProps {
  children: React.ReactNode;
}

export default function PageContainer({ children }: PageContainerProps) {
  return (
    <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8 bg-[#070b14] w-full font-sans">
      <div className="max-w-[1500px] mx-auto w-full space-y-6">
        {children}
      </div>
    </main>
  );
}
