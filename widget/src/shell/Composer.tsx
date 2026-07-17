import { useState, type FormEvent } from 'react';

/** Free-text input + send. Placeholder is supplied by the entry surface
 *  (fixed for Support 1a, rotating for Reports 1b). */
export function Composer({
  placeholder,
  onSend,
  disabled = false,
}: {
  placeholder: string;
  onSend: (text: string) => void;
  disabled?: boolean;
}) {
  const [text, setText] = useState('');

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText('');
  };

  return (
    <form className="composer" onSubmit={submit}>
      <input
        type="text"
        aria-label="Message"
        placeholder={placeholder}
        value={text}
        disabled={disabled}
        onChange={(e) => setText(e.target.value)}
      />
      <button type="submit" className="send" aria-label="Send" disabled={disabled}>
        ➤
      </button>
    </form>
  );
}
