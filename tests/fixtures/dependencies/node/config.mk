BUILD = node -e "if (!require('is-number')(42) || require('fs').readFileSync('installed.txt', 'utf8') !== 'offline') process.exit(1)"
