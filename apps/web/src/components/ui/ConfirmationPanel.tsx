/** P2.28: the end of a task — what was done and its reference, in a panel that stands out and prints well. */
export function ConfirmationPanel({ title, reference, referenceLabel, children }: {
  title: string; reference: string; referenceLabel: string; children?: React.ReactNode;
}) {
  return (
    <div className="ui-confirmation" role="status">
      <h2>{title}</h2>
      <p>{referenceLabel}<br /><strong className="ui-reference">{reference}</strong></p>
      {children}
    </div>
  );
}
