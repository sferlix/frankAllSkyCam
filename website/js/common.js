 
	$(document).ready(function () {
	    $('.menu-icon').click(function () {
        	if ($('#navigator').css("left") == "-250px") {
        	    $('#navigator').animate({left: '0px'}, 350);
        	    $('.menu-icon').animate({left: '250px'}, 350);
        	    $('.menu-text').animate({left: '300px'}, 350).empty().text("");
        	} 
        	else  {
        	    $('#navigator').animate({left: '-250px'}, 350); 
        	    $(this).animate({left: '0px'}, 350);
	            $('.menu-text').animate({left: '50px'}, 350).empty().text("");
	        } 
		});
    		$('.menu-icon').click(function () {
	            $(this).toggleClass("on"); });
	});
 
	function toggleSkyMap() {
	  var x = document.getElementById("starmap");
	  if (x.style.display === "none") {
	    x.style.display = "block";
	  } else {
	    x.style.display = "none";
	  }
	}
 
	function toggleLocation() {
	  var x = document.getElementById("location");
	  if (x.style.display === "none") {
	    x.style.display = "block";
	  } else {
	    x.style.display = "none";
	  }
	}
 