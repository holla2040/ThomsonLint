const fs = require('fs');
const path = require('path');

const jsonPath = 'c:\\_Working_VS\\ThomsonLint\\TestProject\\post_conversion\\TestProject-thomson-export-brd.json';

try {
    const rawData = fs.readFileSync(jsonPath, 'utf-8');
    const data = JSON.parse(rawData);
    
    // 1. Top-level keys
    console.log('=== TOP-LEVEL KEYS ===');
    const keys = Object.keys(data);
    keys.forEach(k => console.log('  - ' + k));
    
    // 2. Number of routes
    console.log('\n=== ROUTES ARRAY COUNT ===');
    const routesCount = (data.routes || []).length;
    console.log('  Total routes: ' + routesCount);
    
    // 3-6. Route details
    if (routesCount > 0) {
        const firstRoute = data.routes[0];
        
        // 3. Route keys
        console.log('\n=== KEYS IN A ROUTE OBJECT ===');
        const routeKeys = Object.keys(firstRoute);
        routeKeys.forEach(k => console.log('  - ' + k));
        
        // 4. Nets
        console.log('\n=== NETS REPRESENTED IN ROUTES ===');
        const uniqueNets = new Set();
        data.routes.forEach(route => {
            if (route.net) {
                uniqueNets.add(route.net);
            }
        });
        const netsArray = Array.from(uniqueNets).sort();
        console.log('  Total unique nets: ' + netsArray.length);
        console.log('  Nets found:');
        netsArray.forEach(net => console.log('    - ' + net));
        
        const v3p3Found = netsArray.some(n => n.toUpperCase() === 'V3P3');
        const gndFound = netsArray.some(n => n.toUpperCase() === 'GND');
        console.log('\n  V3P3 present (case-insensitive): ' + v3p3Found);
        console.log('  GND present (case-insensitive): ' + gndFound);
        
        // 5. Line width
        console.log('\n=== LINE WIDTH / WIDTH FIELD ===');
        console.log('  Has "line_width" field: ' + ('line_width' in firstRoute));
        console.log('  Has "width" field: ' + ('width' in firstRoute));
        if ('line_width' in firstRoute) {
            console.log('  First route line_width value: ' + firstRoute.line_width);
        }
        if ('width' in firstRoute) {
            console.log('  First route width value: ' + firstRoute.width);
        }
        
        // 6. Points structure
        console.log('\n=== POINTS ARRAY STRUCTURE ===');
        if (firstRoute.points && firstRoute.points.length > 0) {
            const points = firstRoute.points;
            console.log('  Total points in first route: ' + points.length);
            
            console.log('\n  First point structure:');
            const pt1 = points[0];
            console.log('    Type: ' + (Array.isArray(pt1) ? 'array' : typeof pt1));
            if (typeof pt1 === 'object' && !Array.isArray(pt1)) {
                Object.keys(pt1).forEach(k => console.log('      - ' + k + ': ' + pt1[k]));
            } else {
                console.log('    Value: ' + JSON.stringify(pt1));
            }
            
            if (points.length > 1) {
                console.log('\n  Second point structure:');
                const pt2 = points[1];
                console.log('    Type: ' + (Array.isArray(pt2) ? 'array' : typeof pt2));
                if (typeof pt2 === 'object' && !Array.isArray(pt2)) {
                    Object.keys(pt2).forEach(k => console.log('      - ' + k + ': ' + pt2[k]));
                } else {
                    console.log('    Value: ' + JSON.stringify(pt2));
                }
            }
        }
    }
} catch (e) {
    console.error('Error: ' + e.message);
    process.exit(1);
}
