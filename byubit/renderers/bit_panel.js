window.renderTracecodePanel = function (root, snapshot) {
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
  root.appendChild(title);

  const world = state.world;
  if (!world || !world.length) return;
  const cellSize = 50;
  const triangleSize = 10;
  const grid = document.createElement('div');
  grid.className = 'grid bit-world-grid';
  grid.style.display = 'grid';
  grid.style.gridTemplateColumns = `repeat(${world[0].length}, ${cellSize}px)`;
  grid.style.gap = '1px';
  grid.style.width = 'max-content';
  grid.style.margin = '0 .55rem .55rem';
  for (let row = world.length - 1; row >= 0; row--) {
    for (let col = 0; col < world[row].length; col++) {
      const cell = document.createElement('div');
      cell.className = 'cell';
      cell.style.width = `${cellSize}px`;
      cell.style.height = `${cellSize}px`;
      cell.style.position = 'relative';
      cell.style.border = '1px solid black';
      cell.style.backgroundColor = world[row][col];
      if (row === state.pos[0] && col === state.pos[1]) {
        const triangle = document.createElement('div');
        triangle.className = 'triangle';
        triangle.style.width = '0';
        triangle.style.height = '0';
        triangle.style.position = 'absolute';
        triangle.style.borderLeft = `${triangleSize}px solid transparent`;
        triangle.style.borderRight = `${triangleSize}px solid transparent`;
        triangle.style.borderBottom = `${triangleSize * 2}px solid cyan`;
        triangle.style.top = `${(cellSize - triangleSize * 2) / 2}px`;
        triangle.style.left = `${(cellSize - triangleSize * 2) / 2}px`;
        triangle.style.transform = ['rotate(90deg)', 'rotate(0deg)', 'rotate(-90deg)', 'rotate(180deg)'][state.orientation];
        cell.appendChild(triangle);
      }
      grid.appendChild(cell);
    }
  }
  root.appendChild(grid);
};
