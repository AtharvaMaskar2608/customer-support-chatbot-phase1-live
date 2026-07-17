import type { TicketConfirmationBlock as Ticket } from '../api/wireTypes';
import { ChipButton } from './ChipButton';

/** Ticket confirmation — ticket id, the SLA/status message, and a
 *  call-support chip. */
export function TicketConfirmationBlock({ block }: { block: Ticket }) {
  return (
    <div className="ticketcard">
      <div className="tk-h">
        🎫 Ticket raised
        <span className="id">{block.ticket_id}</span>
      </div>
      <div className="tk-b">{block.message}</div>
      {block.chips && block.chips.length > 0 && (
        <div className="chips">
          {block.chips.map((chip, i) => (
            <ChipButton key={`${chip.label}-${i}`} chip={chip} />
          ))}
        </div>
      )}
    </div>
  );
}
