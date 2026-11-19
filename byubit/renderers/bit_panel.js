function createBitTriangle(orientation, color, cellSize, size, wrong = false) {
  const triangle = document.createElement('div');
  triangle.className = wrong ? 'triangle wrong' : 'triangle';
  triangle.style.width = '0';
  triangle.style.height = '0';
  triangle.style.position = 'absolute';
  triangle.style.borderLeft = `${size}px solid transparent`;
  triangle.style.borderRight = `${size}px solid transparent`;
  triangle.style.borderBottom = `${size * 2}px solid ${color}`;
  triangle.style.top = `${(cellSize - size * 2) / 2}px`;
  triangle.style.left = `${(cellSize - size * 2) / 2}px`;
  triangle.style.transform = ['rotate(90deg)', 'rotate(0deg)', 'rotate(-90deg)', 'rotate(180deg)'][orientation];
  return triangle;
}

window.renderTracecodePanel = function (root, snapshot) {
  root._bitPanelSnapshot = snapshot;
  if (!root._bitPanelResizeHandler) {
    root._bitPanelResizeHandler = () => window.renderTracecodePanel(root, root._bitPanelSnapshot);
    window.addEventListener('resize', root._bitPanelResizeHandler);
  }
  root.replaceChildren();
  const state = snapshot.bit;
  if (!state) return;

  const title = document.createElement('div');
  title.style.padding = '.35rem .55rem';
  title.style.fontWeight = '600';
  const outcome = snapshot.outcome;
  title.textContent = outcome
    ? `${outcome.status}: ${outcome.message || 'Run finished'}`
    : `${state.name} · (${state.pos[0]}, ${state.pos[1]})`;
  if (outcome?.status === 'error') title.style.color = 'red';
  root.appendChild(title);

  const world = state.world;
  if (!world || !world.length) return;
  const annotations = snapshot.outcome?.annotations;
  const baseCellSize = 50;
  const maxPanelHeight = parseFloat(getComputedStyle(root).maxHeight) || window.innerHeight * 0.9;
  const titleHeight = title.getBoundingClientRect().height;
  const availableWidth = Math.max(1, root.clientWidth - 2 * 8.8 - 1);
  const availableHeight = Math.max(1, maxPanelHeight - titleHeight - 8.8 - 1);
  const cellSize = Math.max(1, Math.min(
    baseCellSize,
    availableWidth / world[0].length,
    availableHeight / world.length,
  ));
  const triangleSize = Math.min(10, cellSize * 0.2);
  const grid = document.createElement('div');
  grid.className = 'grid bit-world-grid';
  grid.style.display = 'grid';
  grid.style.gridTemplateColumns = `repeat(${world[0].length}, ${cellSize}px)`;
  grid.style.gap = '0';
  grid.style.borderTop = '1px solid black';
  grid.style.borderLeft = '1px solid black';
  grid.style.width = 'max-content';
  grid.style.margin = '0 .55rem .55rem';
  for (let row = world.length - 1; row >= 0; row--) {
    for (let col = 0; col < world[row].length; col++) {
      const cell = document.createElement('div');
      cell.className = 'cell';
      cell.style.width = `${cellSize}px`;
      cell.style.height = `${cellSize}px`;
      cell.style.position = 'relative';
      cell.style.boxSizing = 'border-box';
      cell.style.borderRight = '1px solid black';
      cell.style.borderBottom = '1px solid black';
      cell.style.backgroundColor = world[row][col];
      if (row === state.pos[0] && col === state.pos[1]) {
        cell.appendChild(createBitTriangle(state.orientation, 'cyan', cellSize, triangleSize));
      }

      if (annotations?.world?.[row]?.[col] !== undefined
          && annotations.world[row][col] !== world[row][col]) {
        const marker = document.createElement('div');
        marker.className = 'annotation';
        marker.textContent = '!';
        marker.style.width = `${cellSize * 0.4}px`;
        marker.style.height = `${cellSize * 0.6}px`;
        marker.style.fontSize = `${cellSize * 0.32}px`;
        marker.style.borderRadius = '50%';
        marker.style.position = 'absolute';
        marker.style.top = '0';
        marker.style.right = '0';
        marker.style.display = 'flex';
        marker.style.alignItems = 'center';
        marker.style.justifyContent = 'center';
        marker.style.color = annotations.world[row][col] === 'white' ? 'black' : 'white';
        marker.style.fontWeight = 'bold';
        marker.style.backgroundColor = annotations.world[row][col];
        cell.appendChild(marker);
      }

      if (annotations?.pos?.[0] === row && annotations.pos[1] === col
          && (row !== state.pos[0] || col !== state.pos[1])) {
        cell.appendChild(createBitTriangle(annotations.orientation, '#8bbab5', cellSize, triangleSize, true));
      }
      grid.appendChild(cell);
    }
  }
  root.appendChild(grid);
};
