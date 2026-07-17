import type { StepperCardBlock as Stepper } from '../api/wireTypes';
import { ChipButton } from './ChipButton';
import { useBlockActions } from './context';

/**
 * Editable multi-step card. Completed (`done`) steps show the chosen value and
 * stay tappable to edit: tapping one dispatches a reopen turn for that step.id,
 * and the server clears all downstream selections (spec §8.4). The widget holds
 * no stepper state of its own — it renders whatever stepper block the server
 * last sent and emits actions; the server owns cache/refetch.
 */
export function StepperCardBlock({ block }: { block: Stepper }) {
  const { dispatch } = useBlockActions();

  return (
    <div className="stepper">
      {block.steps.map((step, i) => {
        const done = step.state === 'done';
        const active = step.state === 'active';
        const cls = `step ${step.state}`;
        const numContent = done ? '✓' : i + 1;
        const body = (
          <div className="sbody">
            <div className={active || done ? 'slabel' : 'slabel muted'}>{step.title}</div>
            {done && step.selected_label && (
              <div className="sval">
                {step.selected_label}
                <span className="edit">Edit</span>
              </div>
            )}
            {active && step.chips && step.chips.length > 0 && (
              <div className="chips">
                {step.chips.map((chip, ci) => (
                  <ChipButton key={`${chip.label}-${ci}`} chip={chip} primary={ci === 0} />
                ))}
              </div>
            )}
          </div>
        );

        if (done) {
          return (
            <button
              type="button"
              className={cls}
              key={step.id}
              aria-label={`Edit ${step.title}`}
              onClick={() => dispatch({ kind: 'select_param', payload: { step: step.id, reopen: '1' } })}
            >
              <span className="snum">{numContent}</span>
              {body}
            </button>
          );
        }
        return (
          <div className={cls} key={step.id}>
            <span className="snum">{numContent}</span>
            {body}
          </div>
        );
      })}
    </div>
  );
}
