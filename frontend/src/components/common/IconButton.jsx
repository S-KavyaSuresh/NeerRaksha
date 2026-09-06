export default function IconButton({ label, children, ...props }) {
  return <button className="icon-button" title={label} aria-label={label} {...props}>{children}</button>
}
