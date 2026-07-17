/** Widget header: avatar ✦, online status with Client ID, and Start over. */
export function Header({ clientId, onStartOver }: { clientId: string; onStartOver: () => void }) {
  return (
    <div className="wg-head">
      <div className="ava">✦</div>
      <div className="wg-id">
        <b>Choice Jini</b>
        <span>
          <i className="dot" />
          online · {clientId}
        </span>
      </div>
      <button type="button" className="startover" onClick={onStartOver}>
        ↺ Start over
      </button>
    </div>
  );
}
