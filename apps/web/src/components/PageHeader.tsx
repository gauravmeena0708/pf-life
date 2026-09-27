import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

interface PageHeaderProps {
  id?: string;
  eyebrow: string;
  title: string;
  description: string;
  current?: string;
  parent?: { label: string; to: string };
  children?: React.ReactNode;
}

export function PageHeader({ id, eyebrow, title, description, current, parent, children }: PageHeaderProps) {
  const { t } = useTranslation();
  return (
    <header className="page-header">
      {current ? <nav aria-label={t("navigation.breadcrumb")} className="breadcrumb">
        <Link to="/">{t("navigation.home")}</Link>
        {parent ? <><span aria-hidden="true">›</span><Link to={parent.to}>{parent.label}</Link></> : null}
        <span aria-hidden="true">›</span><span aria-current="page">{current}</span>
      </nav> : null}
      <div className="page-header-row">
        <div><p className="eyebrow">{eyebrow}</p><h1 id={id}>{title}</h1><p className="page-description">{description}</p></div>
        {children}
      </div>
    </header>
  );
}
