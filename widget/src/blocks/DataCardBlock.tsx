import type { DataCardBlock as DataCard } from '../api/wireTypes';

/** Brokerage / holdings card. Iterates whatever groups/rows the server returns
 *  and renders `value` VERBATIM — no computed rupee figures, no hardcoded
 *  segment names or row counts (spec §8.4). */
export function DataCardBlock({ block }: { block: DataCard }) {
  return (
    <div className="datacard">
      {block.groups.map((group, gi) => (
        <div className="dgrp" key={`${group.title}-${gi}`}>
          <div className="dgt">{group.title}</div>
          {group.list.map((row, ri) => (
            <div className="drow" key={`${row.label}-${ri}`}>
              <span className="dk">{row.label}</span>
              <span className="dv">{row.value}</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
