import Toybox.Lang;
import Toybox.WatchUi;

class venu3sappDelegate extends WatchUi.BehaviorDelegate {

    function initialize() {
        BehaviorDelegate.initialize();
    }

    function onMenu() as Boolean {
        WatchUi.pushView(new Rez.Menus.MainMenu(), new venu3sappMenuDelegate(), WatchUi.SLIDE_UP);
        return true;
    }

}