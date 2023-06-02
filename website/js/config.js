	var planetarium;
	S(document).ready(function() {
	planetarium = S.virtualsky({
		id: 'starmap',	// This should match the ID used in the DOM
		constellationlabels:false,
		gradient:false,
		magnitude:4,
		mouse:false,
                keyboard:false,
		constellations:true,
		showdate:false,
		showposition:false,
		transparent:true,
		latitude:25.0,
		longitude:15.0,
                fontsize:10,
                language:'en',
                live:true,
		az:152,                 
		});
        starmap.style.display = "none";
	});