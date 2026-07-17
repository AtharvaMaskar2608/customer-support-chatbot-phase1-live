import type { BubbleBlock as Bubble, UserBubbleBlock } from '../api/wireTypes';

const TRUST_LINE = 'Files land right here — no email verification.';

/** Bot bubble (left). When `compliance_footer` is set, the persistent
 *  disclaimer + trust line are appended inside the bubble (spec: RAG answers
 *  and compliance-relevant replies carry it). */
export function BubbleBlock({ block }: { block: Bubble }) {
  return (
    <div className="msg l">
      <div className="bub bot">
        {block.text}
        {block.compliance_footer && (
          <span className="em">Factual answers only — never investment advice. {TRUST_LINE}</span>
        )}
      </div>
    </div>
  );
}

/** User bubble (right, white). The SERVER echoes the user's turn as a
 *  user_bubble; the widget renders it and never synthesizes its own. */
export function UserBubbleBlock({ block }: { block: UserBubbleBlock }) {
  return (
    <div className="msg r">
      <div className="bub user">{block.text}</div>
    </div>
  );
}
