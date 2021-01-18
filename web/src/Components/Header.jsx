import React from 'react';
import AppBar from '@material-ui/core/AppBar';
import Grid from '@material-ui/core/Grid';
import Hidden from '@material-ui/core/Hidden';
import IconButton from '@material-ui/core/IconButton';
import MenuIcon from '@material-ui/icons/Menu';
import Toolbar from '@material-ui/core/Toolbar';
import makeStyles from '@material-ui/core/styles/makeStyles';
import Chip from '@material-ui/core/Chip';

const useStyles = makeStyles((theme) => ({
  menuButton: {
    marginLeft: -theme.spacing(1),
  },
  avatar: {
    'display': 'flex',
    '& > *': {
      margin: theme.spacing(1),
    },
  },
}));

export default function Header({onDrawerToggle, user}) {
  const classes = useStyles();

  return (
    <React.Fragment>
      <AppBar color="primary" position="sticky" elevation={0}>
        <Toolbar>
          <Grid container spacing={1} alignItems="center">
            <Hidden smUp>
              <Grid item>
                <IconButton
                  color="inherit"
                  aria-label="open drawer"
                  onClick={onDrawerToggle}
                  className={classes.menuButton}
                >
                  <MenuIcon/>
                </IconButton>
              </Grid>
            </Hidden>
            <Grid item xs/>
            <Grid item>
              <div className={classes.avatar}>
                <Chip clickable label={user?.netid}/>
              </div>
            </Grid>
          </Grid>
        </Toolbar>
      </AppBar>
    </React.Fragment>
  );
}
