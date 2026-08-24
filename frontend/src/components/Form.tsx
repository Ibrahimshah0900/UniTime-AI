import { cloneElement, useId, type InputHTMLAttributes, type ReactElement, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react'

type LabelledControlProps = { id?: string; 'aria-describedby'?: string }

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactElement<LabelledControlProps> }) {
  const generatedId = useId()
  const controlId = children.props.id || generatedId
  const hintId = `${controlId}-hint`
  const describedBy = [children.props['aria-describedby'], hint ? hintId : ''].filter(Boolean).join(' ') || undefined
  const control = cloneElement(children, { id: controlId, 'aria-describedby': describedBy })
  return <div className="field"><label htmlFor={controlId}>{label}</label>{control}{hint && <small id={hintId}>{hint}</small>}</div>
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) { return <input className="input" {...props}/> }
export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) { return <select className="input" {...props}/> }
export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) { return <textarea className="input textarea" {...props}/> }
