import { FileText, Layers, Zap } from "lucide-react";

interface StatusWidgetProps {
  planName: string;
  pageBalance: number;
  pageLimit: number;
  extraPages: number;
  isLoading?: boolean;
}

const StatusWidget = ({ planName, pageBalance, pageLimit, extraPages, isLoading }: StatusWidgetProps) => {
  const percentage = pageLimit > 0 ? (pageBalance / pageLimit) * 100 : 0;
  const isLow = percentage <= 20;

  if (isLoading) {
    return (
      <div className="flex items-center gap-3 px-4 py-2 rounded-full bg-surface border border-border/50">
        <div className="skeleton-pulse h-4 w-16" />
        <div className="w-px h-5 bg-border" />
        <div className="skeleton-pulse h-4 w-20" />
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3 px-4 py-2 rounded-full bg-surface/80 border border-border/50 backdrop-blur-sm">
      <div className="flex items-center gap-1.5">
        <Layers className="w-3.5 h-3.5 text-primary" />
        <span className="text-xs font-medium text-foreground">{planName}</span>
      </div>
      <div className="w-px h-5 bg-border" />
      <div className="flex items-center gap-1.5">
        <FileText className="w-3.5 h-3.5 text-primary" />
        <span className={`text-xs font-semibold ${isLow ? "text-warning" : "text-foreground"}`}>
          {pageBalance} / {pageLimit}
        </span>
      </div>
      {extraPages > 0 && (
        <>
          <div className="w-px h-5 bg-border" />
          <div className="flex items-center gap-1.5">
            <Zap className="w-3.5 h-3.5 text-success" />
            <span className="text-xs font-medium text-success">+{extraPages}</span>
          </div>
        </>
      )}
    </div>
  );
};

export default StatusWidget;
